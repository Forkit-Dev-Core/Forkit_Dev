"""Build an offline bundle for this interpreter/platform from local checked wheels."""

from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path

from install_radar import PROJECTS, digest, pip, wheel_lock

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project-wheels", type=Path, required=True)
    parser.add_argument("--wheelhouse", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Output exists; use a new filename")
    with tempfile.TemporaryDirectory(prefix="forkit-bundle-") as temporary:
        root = Path(temporary)
        wheels = root / "wheels"
        wheels.mkdir()
        pip(sys.executable, "download", ["--no-deps", "-r", ROOT / "requirements/radar-runtime.lock", "--dest", wheels],
            cwd=root, wheelhouse=args.wheelhouse.resolve(), offline=True)
        for name in sorted(PROJECTS):
            shutil.copyfile(args.project_wheels / name, wheels / name)
        shutil.copyfile(ROOT / "scripts/install_radar.py", root / "install.py")
        shutil.copyfile(ROOT / "packages/radar/LICENSE", root / "LICENSE")
        wheel_lock(wheels, root / "requirements.lock")
        python = f"{sys.version_info.major}.{sys.version_info.minor}"
        (root / "README.txt").write_text(
            f"Forkit Session Receipt open-source beta 0.1.0b5\n"
            f"Platform: {sys.platform} {platform.machine()} | Python {python}\n\n"
            "Start by opening START_HERE.html. Then run: sh install.sh\n"
            "Check prerequisites first: sh install.sh --check\n"
            "macOS: Install.command is a convenience launcher, not a signed app.\n"
            "No network, account or login required. Requires a compatible Python with venv/pip.\n"
            "Installs to ~/.local/share/forkit-radar; command ~/.local/bin/forkit-radar.\n"
            "Existing installations/commands are refused, never overwritten.\n"
            "Use --prefix and --bin-dir for separate custom destinations.\n"
            "Installation configures detected tools once. Codex: review Forkit in /hooks, then start a new session.\n"
            "Open local history: forkit-radar open; on Mac use the installed Finder launcher.\n"
            "Skip integration: --no-capture. Pause: forkit-radar setup --disable.\n"
            "Review: forkit-radar receipt | forkit-radar history (run separately)\n"
            "Card: forkit-radar card --output receipt.html (open it to save PNG)\n"
            "Local data remains in ~/.forkit-radar. Usage reporting is off until new explicit consent.\n"
            "Agent command authentication/network requirements are independent.\n"
            "Checksums detect changes within this bundle; they do not authenticate its publisher.\n"
            "Forkit is Apache-2.0; third-party wheel licenses are retained inside each wheel.\n"
        )
        shutil.copyfile(ROOT / "packages/radar/CAPTURE.md", root / "CAPTURE.md")
        shutil.copyfile(ROOT / "packages/radar/MACOS.md", root / "MACOS.md")
        kit = ROOT / "packages/radar/beta-kit"
        for name in ("START_HERE.html", "USAGE.md", "BETA.md"):
            shutil.copyfile(kit / name, root / name)
        shell = (ROOT / "scripts/install_radar.sh").read_text().replace("FORKIT_REQUIRED_MINOR=''", "FORKIT_REQUIRED_MINOR='" + python + "'").replace("FORKIT_INSTALLER='install_radar.py'", "FORKIT_INSTALLER='install.py'")
        for name in ("install.sh", "Install.command"):
            (root / name).write_text(shell)
        manifest = {
            "format": 1, "python": python, "platform": sys.platform, "machine": platform.machine(),
            "sha256": {str(p.relative_to(root)): digest(p) for p in sorted(root.rglob("*")) if p.is_file()},
        }
        (root / "bundle.json").write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(args.output, "x", compression=zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(root.rglob("*")):
                if path.is_file():
                    item = zipfile.ZipInfo("forkit-session-receipt/" + str(path.relative_to(root)), (2023, 11, 14, 22, 13, 20))
                    item.external_attr = (0o100755 if path.name in {"install.sh", "Install.command"} else 0o100644) << 16
                    archive.writestr(item, path.read_bytes(), compress_type=zipfile.ZIP_DEFLATED)
    print(json.dumps({"bundle": str(args.output), "sha256": digest(args.output)}, indent=2))


if __name__ == "__main__":
    main()
