"""Bootstrap boundaries without installing anything into the user's home."""

import argparse
import importlib.util
import json
import os
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "install_radar.py"


@pytest.fixture
def installer():
    spec = importlib.util.spec_from_file_location("radar_bootstrap", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def args(tmp_path, **updates):
    return argparse.Namespace(**{**dict(prefix=tmp_path / "app", bin_dir=tmp_path / "bin",
                                       offline=True, wheelhouse=tmp_path / "wheels"), **updates})


def test_existing_app_never_modified(installer, tmp_path):
    destination = tmp_path / "app"
    destination.mkdir()
    (destination / "keep").write_text("original")
    with pytest.raises(ValueError, match="already exists"):
        installer.install(args(tmp_path))
    assert (destination / "keep").read_text() == "original"


def test_mac_launcher_uses_installed_python_without_shell_interpolation(installer, tmp_path):
    import plistlib
    import shlex
    destination = tmp_path / 'Applications/Forkit Session Receipt.app'
    python = tmp_path / "python ' space $(never-executed)"
    installer.mac_launcher(python, destination)
    command = destination / 'Contents/MacOS/Forkit'
    assert command.stat().st_mode & 0o777 == 0o755
    assert shlex.split(command.read_text().splitlines()[1]) == ['exec', str(python), '-I', '-m', 'forkit_radar', 'open']
    plist = plistlib.loads((destination / 'Contents/Info.plist').read_bytes())
    assert plist['CFBundleExecutable'] == 'Forkit'
    assert not any('UsageDescription' in key for key in plist)
    before = command.read_bytes()
    with pytest.raises(ValueError, match='already exists'):
        installer.mac_launcher(python, destination)
    assert command.read_bytes() == before


def test_skipped_capture_does_not_mutate_tool_configuration(installer, tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('setup or launcher attempted')
    monkeypatch.setattr(installer.subprocess, 'run', forbidden)
    monkeypatch.setattr(installer, 'mac_launcher', forbidden)
    installer.finish_setup(tmp_path/'python', args(tmp_path, no_capture=True, no_app=True), tmp_path/'forkit')


@pytest.mark.parametrize("kind", ["file", "symlink", "broken_symlink"])
def test_existing_command_never_replaced(installer, tmp_path, kind):
    directory = tmp_path / "bin"
    directory.mkdir()
    command = directory / "forkit-radar"
    if kind == "file":
        command.write_text("original")
    else:
        target = tmp_path / "target"
        if kind == "symlink":
            target.write_text("original")
        command.symlink_to(target)
    with pytest.raises(ValueError, match="already exists"):
        installer.install(args(tmp_path))
    assert not (tmp_path / "app").exists()
    assert command.is_symlink() if kind != "file" else command.read_text() == "original"


def test_symlink_parent_and_data_directory_refused(installer, tmp_path):
    (tmp_path / "real").mkdir()
    (tmp_path / "link").symlink_to(tmp_path / "real", target_is_directory=True)
    with pytest.raises(ValueError, match="Symlinked"):
        installer.install(args(tmp_path, prefix=tmp_path / "link/app"))
    with pytest.raises(ValueError, match="private data"):
        installer.install(args(tmp_path, prefix=tmp_path / ".forkit-radar"))


def test_failed_bootstrap_removes_only_fresh_install(installer, tmp_path, monkeypatch):
    def fail(*_args, **_kwargs):
        raise OSError("simulated failure")

    monkeypatch.setattr(installer.venv.EnvBuilder, "create", fail)
    with pytest.raises(OSError, match="simulated failure"):
        installer.install(args(tmp_path))
    assert not (tmp_path / "app").exists()
    assert not (tmp_path / "bin/forkit-radar").exists()


def test_pip_environment_ignores_private_config_and_credentials(installer, monkeypatch):
    monkeypatch.setenv("PIP_INDEX_URL", "https://private:secret@example.invalid")
    monkeypatch.setenv("PIP_EXTRA_INDEX_URL", "https://extra.invalid")
    monkeypatch.setenv("PYTHONPATH", "/private/inject")
    env = installer.environment()
    assert "PIP_INDEX_URL" not in env and "PIP_EXTRA_INDEX_URL" not in env
    assert "PYTHONPATH" not in env
    assert env["PIP_CONFIG_FILE"] == os.devnull
    assert env["NETRC"] == os.devnull
    assert env["PIP_KEYRING_PROVIDER"] == "disabled"


@pytest.mark.parametrize("raw", ["null", "[]", "42", "true", '"text"', "x" * 1_048_577])
def test_malformed_bundle_shape_refused(installer, tmp_path, raw):
    (tmp_path / "bundle.json").write_text(raw)
    with pytest.raises(ValueError):
        installer.checked_bundle(tmp_path)


@pytest.mark.parametrize("change", ["checksum", "path", "platform", "lock_directive", "extra_wheel"])
def test_bundle_tampering_refused(installer, tmp_path, change):
    wheels = tmp_path / "wheels"
    wheels.mkdir()
    for name in installer.PROJECTS:
        (wheels / name).write_bytes(b"placeholder for inventory validation")
    (tmp_path / "install.py").write_text("# trusted bootstrap placeholder")
    installer.wheel_lock(wheels, tmp_path / "requirements.lock")
    manifest = {"format": 1, "python": f"{installer.sys.version_info.major}.{installer.sys.version_info.minor}",
                "platform": installer.sys.platform, "machine": installer.platform.machine(),
                "sha256": {str(p.relative_to(tmp_path)): installer.digest(p) for p in tmp_path.rglob("*") if p.is_file()}}
    if change == "checksum":
        (tmp_path / "requirements.lock").write_text("changed")
    elif change == "path":
        manifest["sha256"]["../private"] = "0" * 64
    elif change == "platform":
        manifest["platform"] = "unvalidated-platform"
    elif change == "lock_directive":
        (tmp_path / "requirements.lock").write_text("--extra-index-url https://untrusted.invalid\n")
        manifest["sha256"]["requirements.lock"] = installer.digest(tmp_path / "requirements.lock")
    else:
        (wheels / "extra-1.0-py3-none-any.whl").write_bytes(b"extra")
    (tmp_path / "bundle.json").write_text(json.dumps(manifest))
    with pytest.raises(ValueError):
        installer.checked_bundle(tmp_path)


def test_prerequisite_check_does_not_install_or_download(installer, tmp_path, monkeypatch, capsys):
    def forbidden(*_args, **_kwargs):
        raise AssertionError('installation attempted')
    monkeypatch.setattr(installer.venv.EnvBuilder, 'create', forbidden)
    monkeypatch.setattr(installer, 'pip', forbidden)
    installer.install(args(tmp_path, check=True))
    assert not (tmp_path / 'app').exists()
    assert not (tmp_path / 'bin').exists()
    assert 'Nothing installed' in capsys.readouterr().out


@pytest.mark.parametrize('failure', ['git', 'ensurepip', 'space'])
def test_missing_prerequisite_refuses_before_creating_destination(installer, tmp_path, monkeypatch, failure):
    if failure == 'git':
        def unavailable(*_args, **_kwargs):
            raise OSError('not installed')
        monkeypatch.setattr(installer.subprocess, 'run', unavailable)
    elif failure == 'ensurepip':
        monkeypatch.setattr(installer.importlib.util, 'find_spec', lambda _: None)
    else:
        from types import SimpleNamespace
        monkeypatch.setattr(installer.shutil, 'disk_usage', lambda _: SimpleNamespace(free=0))
    with pytest.raises(ValueError):
        installer.install(args(tmp_path, check=True))
    assert not (tmp_path / 'app').exists()


def test_shell_bootstrap_real_python_and_space_arguments(tmp_path):
    import subprocess
    import sys
    env = dict(os.environ)
    commands = tmp_path / 'commands'
    commands.mkdir()
    (commands / 'python3').symlink_to(sys.executable)
    env['PATH'] = str(commands) + os.pathsep + os.environ.get('PATH', '')
    result = subprocess.run(['/bin/sh', str(SCRIPT.with_suffix('.sh')), '--check', '--prefix', str(tmp_path / 'space app'), '--bin-dir', str(tmp_path / 'space bin')], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'Nothing installed' in result.stdout
    assert not (tmp_path / 'space app').exists()
