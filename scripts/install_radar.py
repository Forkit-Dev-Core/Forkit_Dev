#!/usr/bin/env python3
"""Install this source checkout, or an extracted local bundle, without an account.

Standard-library bootstrap. Never resolves Forkit packages by their public names.
Existing installations/commands are left untouched; no shell profile is edited.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import plistlib
import re
import shlex
import shutil
import subprocess
import sys
import tempfile
import venv
from pathlib import Path

PROJECTS = {"forkit_core-0.1.0-py3-none-any.whl", "forkit_radar-0.1.0b5-py3-none-any.whl"}


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def environment():
    env = {k: v for k, v in os.environ.items() if not k.startswith(("PIP_", "PYTHON"))}
    env.update(PIP_CONFIG_FILE=os.devnull, PIP_NO_INPUT="1", PIP_DISABLE_PIP_VERSION_CHECK="1",
               PIP_KEYRING_PROVIDER="disabled", NETRC=os.devnull,
               PYTHONDONTWRITEBYTECODE="1", SOURCE_DATE_EPOCH="1704067200")
    return env


def run(argv, *, cwd):
    subprocess.run([str(a) for a in argv], cwd=cwd, env=environment(), check=True)


def pip(python, action, arguments, *, cwd, wheelhouse=None, offline=False):
    run([python, "-I", "-m", "pip", action, "--no-input", "--disable-pip-version-check",
         "--only-binary=:all:", "--require-hashes",
         *( ["--no-index"] if offline else ["--index-url", "https://pypi.org/simple"] ),
         *( ["--find-links", wheelhouse] if wheelhouse else [] ), *arguments], cwd=cwd)


def safe_path(path):
    path = path.expanduser().absolute()
    for part in [*reversed(path.parents), path]:
        if part.is_symlink():
            raise ValueError("Symlinked installation paths are not supported; select a physical path.")
        if part.exists() and not part.is_dir():
            raise ValueError("Installation parent is not a directory.")
    if any(ord(c) < 32 for c in str(path)):
        raise ValueError("Control characters in installation paths are not supported.")
    return path


def wheel_lock(directory, destination):
    wheels = sorted(directory.glob("*.whl"))
    names = {w.name for w in wheels}
    if not PROJECTS.issubset(names):
        raise ValueError("Both locally built Forkit wheels are required.")
    lines = []
    for wheel in wheels:
        if wheel.is_symlink() or not re.fullmatch(r"[A-Za-z0-9_.+\-]+\.whl", wheel.name):
            raise ValueError("Invalid wheel file.")
        name, version = wheel.name.split("-")[:2]
        lines.append(f"{name.replace('_', '-')}=={version} --hash=sha256:{digest(wheel)}")
    destination.write_text("\n".join(lines) + "\n")


def checked_bundle(root):
    path = root / "bundle.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("Missing or unsafe bundle manifest.")
    with path.open("rb") as handle:
        raw = handle.read(1_048_577)
    if len(raw) > 1_048_576:
        raise ValueError("Oversized bundle manifest.")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or set(manifest) != {"format", "python", "platform", "machine", "sha256"} or type(manifest["format"]) is not int or manifest["format"] != 1:
        raise ValueError("Unsupported bundle manifest.")
    if (manifest["python"], manifest["platform"], manifest["machine"]) != (
        f"{sys.version_info.major}.{sys.version_info.minor}", sys.platform, platform.machine()
    ):
        raise ValueError("Bundle requires the Python minor version and platform shown in its README.")
    hashes = manifest["sha256"]
    if not isinstance(hashes, dict) or not 4 <= len(hashes) <= 40:
        raise ValueError("Invalid bundle file inventory.")
    for name, expected in hashes.items():
        if name not in {"install.py", "install.sh", "Install.command", "START_HERE.html", "USAGE.md", "BETA.md", "CAPTURE.md", "MACOS.md", "requirements.lock", "README.txt", "LICENSE"} and not re.fullmatch(
            r"wheels/[A-Za-z0-9_.+\-]+\.whl", name
        ):
            raise ValueError("Unexpected bundle file.")
        path = root / name
        if path.is_symlink() or (root / "wheels").is_symlink() or not path.is_file():
            raise ValueError("Bundle file missing or unsafe.")
        if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected) or digest(path) != expected:
            raise ValueError("Bundle checksum mismatch; nothing installed.")
    if not {"install.py", "requirements.lock", *("wheels/" + p for p in PROJECTS)}.issubset(hashes):
        raise ValueError("Incomplete bundle.")
    # The lock must describe exactly the inspected wheels, without extra pip directives.
    with tempfile.TemporaryDirectory(prefix="forkit-bundle-check-") as temporary:
        lock = Path(temporary) / "requirements.lock"
        wheel_lock(root / "wheels", lock)
        if lock.read_bytes() != (root / "requirements.lock").read_bytes():
            raise ValueError("Bundle requirements do not match the wheel inventory.")
    if {p.name for p in (root / "wheels").iterdir()} != {
        name.split("/")[1] for name in hashes if name.startswith("wheels/")
    }:
        raise ValueError("Unexpected bundle wheel contents.")
    return root / "wheels", root / "requirements.lock"


def mac_launcher(python, destination):
    """A local Finder launcher, not a signed or self-contained distribution."""
    parent = safe_path(destination.parent)
    if destination.exists() or destination.is_symlink():
        raise ValueError('The Finder launcher already exists; it was left unchanged.')
    parent.mkdir(parents=True, exist_ok=True)
    destination.mkdir(mode=0o700)
    try:
        contents = destination / 'Contents'
        executable = contents / 'MacOS/Forkit'
        executable.parent.mkdir(parents=True)
        executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' -I -m forkit_radar open\n')
        executable.chmod(0o755)
        (contents / 'Info.plist').write_bytes(plistlib.dumps({
            'CFBundleName': 'Forkit Session Receipt', 'CFBundleDisplayName': 'Forkit Session Receipt',
            'CFBundleIdentifier': 'dev.forkit.sessionreceipt.local', 'CFBundlePackageType': 'APPL',
            'CFBundleExecutable': 'Forkit', 'CFBundleVersion': '4', 'CFBundleShortVersionString': '0.1.0b5',
            'LSUIElement': True,
        }))
    except Exception:
        shutil.rmtree(destination)
        raise
    return destination


def finish_setup(python, args, launcher):
    command = shlex.quote(str(launcher))
    if not getattr(args, 'no_capture', False):
        print('\nSetting up automatic capture for detected coding tools. Local Git projects only; no upload.', flush=True)
        try:
            result = subprocess.run([str(python), '-I', '-m', 'forkit_radar', 'setup'], env=environment(),
                                    stdin=subprocess.DEVNULL, timeout=30)
            configured = result.returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            configured = False
        if not configured:
            print('Forkit is installed, but automatic capture needs attention. Run ' + command + ' setup --status.')
    else:
        print('Automatic capture was skipped. Enable later with: ' + command + ' setup')
    if sys.platform == 'darwin' and not getattr(args, 'no_app', False):
        destination = Path.home() / 'Applications/Forkit Session Receipt.app'
        try:
            mac_launcher(python, destination)
            print('Open Forkit Session Receipt in your Applications folder to see local history.')
        except (ValueError, OSError):
            print('Finder launcher needs attention. Open local history with: ' + command + ' open')
    else:
        print('Open local history with: ' + command + ' open')
    print('Codex requires one review of the new Forkit definitions in /hooks. No trust bypass is installed.')
    print('Then start a new coding session normally. No repository connection or Forkit account.')
    print('Pause automatic capture: ' + command + ' setup --disable')
    print('Manual fallback: ' + command + ' start --tool cursor, then ' + command + ' stop')


def install(args):
    if os.name != "posix" or not (3, 10) <= sys.version_info[:2] <= (3, 13):
        raise ValueError("This beta installer requires macOS/Linux and Python 3.10–3.13 with venv/pip.")
    prefix, bin_dir = safe_path(args.prefix), safe_path(args.bin_dir)
    launcher = bin_dir / "forkit-radar"
    if prefix.exists() or launcher.exists() or launcher.is_symlink():
        raise ValueError("Installation or command already exists. It was left unchanged; choose new --prefix and --bin-dir paths.")
    if prefix == bin_dir or prefix in bin_dir.parents or bin_dir in prefix.parents:
        raise ValueError("Choose separate installation and command directories.")
    if ".forkit-radar" in prefix.parts or ".forkit" in prefix.parts:
        raise ValueError("Install application files outside Forkit's private data directories.")
    here = Path(__file__).resolve().parent
    bundle = (here / "bundle.json").exists()
    wheels, lock = checked_bundle(here) if bundle else (None, None)
    source = here.parent
    if not bundle and not (source / "packages/radar/pyproject.toml").is_file():
        raise ValueError("Run this installer from the complete Forkit source checkout or extracted bundle.")
    if args.offline and not bundle and args.wheelhouse is None:
        raise ValueError("Offline source installation needs --wheelhouse with build and runtime wheels.")
    wheelhouse = args.wheelhouse.resolve() if args.wheelhouse else None
    if importlib.util.find_spec("ensurepip") is None:
        raise ValueError("Python venv/pip is missing. On Ubuntu install the matching python3-venv package, then retry. No application installed.")
    try:
        git = subprocess.run(["/usr/bin/git", "--version"], env=environment(), stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10)
        if git.returncode:
            raise ValueError("Git is unavailable. Install Git before capturing sessions.")
    except (OSError, subprocess.TimeoutExpired):
        raise ValueError("Git is unavailable. Install Git before capturing sessions.") from None
    ancestor = prefix.parent
    while not ancestor.exists():
        ancestor = ancestor.parent
    if shutil.disk_usage(ancestor).free < 268_435_456:
        raise ValueError("At least 256 MiB free disk space is required for installation.")
    if getattr(args, "check", False):
        print("Ready to install. Python, Git, destinations" + (" and bundle checksums" if bundle else "") + " checked. Nothing installed; no network request made.")
        return
    # Reserve a fresh destination exclusively; a failed attempt cannot alter an old install.
    prefix.parent.mkdir(parents=True, exist_ok=True)
    prefix.mkdir(mode=0o700)
    activated = False
    try:
        python = prefix / "venv/bin/python"
        venv.EnvBuilder(with_pip=True).create(prefix / "venv")
        if not bundle:
            with tempfile.TemporaryDirectory(prefix="build-", dir=prefix) as temporary:
                build = Path(temporary)
                venv.EnvBuilder(with_pip=True).create(build / "env")
                builder = build / "env/bin/python"
                pip(builder, "install", ["-r", source / "requirements/radar-build.lock"],
                    cwd=build, wheelhouse=wheelhouse, offline=args.offline)
                wheels = build / "wheels"
                for project in (source, source / "packages/radar"):
                    run([builder, "-I", "-m", "build", "--wheel", "--no-isolation", "--outdir", wheels, project], cwd=build)
                lock = build / "projects.lock"
                wheel_lock(wheels, lock)
                pip(python, "install", ["-r", source / "requirements/radar-runtime.lock"],
                    cwd=prefix, wheelhouse=wheelhouse, offline=args.offline)
                pip(python, "install", ["--no-deps", "-r", lock], cwd=prefix, wheelhouse=wheels, offline=True)
        else:
            pip(python, "install", ["--no-deps", "-r", lock], cwd=prefix, wheelhouse=wheels, offline=True)
        run([python, "-I", "-m", "pip", "check"], cwd=prefix)
        run([python, "-I", "-m", "forkit_radar.cli", "--version"], cwd=prefix)
        (prefix / "installation.json").write_text(json.dumps({
            "format": 1, "command": str(launcher), "mode": "offline_bundle" if bundle else "source",
            "data_directory": "unchanged",
        }, indent=2) + "\n")
        os.chmod(prefix / "installation.json", 0o600)
        bin_dir.mkdir(parents=True, exist_ok=True)
        safe_path(bin_dir)
        # Same-directory hard-link activation is atomic and cannot overwrite a command.
        descriptor, name = tempfile.mkstemp(prefix=".forkit-install-", dir=bin_dir)
        try:
            with os.fdopen(descriptor, "w") as handle:
                handle.write("#!/bin/sh\n# Forkit local OSS launcher\nexec " + shlex.quote(str(python)) + ' -I -m forkit_radar.cli "$@"\n')
                handle.flush()
                os.fchmod(handle.fileno(), 0o755)
                os.fsync(handle.fileno())
            os.link(name, launcher)
            activated = True
        finally:
            Path(name).unlink(missing_ok=True)
    finally:
        if not activated:
            shutil.rmtree(prefix)
    print("\nForkit installed locally. No signup, login or shell-profile changes.")
    command = shlex.quote(str(launcher))
    finish_setup(python, args, launcher)
    print(command + " history")
    print(command + " card --output receipt.html")
    if str(bin_dir) not in os.environ.get("PATH", "").split(os.pathsep):
        print("Use the full command path above, or add this directory to PATH yourself: " + str(bin_dir))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prefix", type=Path, default=Path.home() / ".local/share/forkit-radar")
    parser.add_argument("--bin-dir", type=Path, default=Path.home() / ".local/bin")
    parser.add_argument("--wheelhouse", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--check", action="store_true", help="Check prerequisites and destinations without installing or downloading")
    parser.add_argument('--no-capture', action='store_true', help='Install without configuring coding-tool hooks')
    parser.add_argument('--no-app', action='store_true', help='Do not create the macOS Finder launcher')
    args = parser.parse_args()
    try:
        install(args)
    except (ValueError, OSError, subprocess.CalledProcessError) as error:
        print(f"Forkit installation stopped: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
