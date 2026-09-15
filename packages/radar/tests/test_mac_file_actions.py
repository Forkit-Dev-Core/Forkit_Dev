"""The native helper must be the pinned, owned file in this runtime's bundle."""
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from forkit_radar import mac_file_actions as actions
from forkit_radar.jsonio import ContractError


def test_native_helper_rejects_tampering_and_links(tmp_path, monkeypatch):
    app = tmp_path / 'Forkit Session Receipt.app'
    python = app / 'Contents/Resources/runtime/bin/python3.11'
    python.parent.mkdir(parents=True)
    python.write_bytes(b'fixture interpreter')
    helper = app / 'Contents/MacOS/ForkitFileActions'
    helper.parent.mkdir()
    helper.write_bytes(b'controlled helper bytes; never executed')
    helper.chmod(0o700)
    marker = app / 'Contents/Resources/forkit-file-actions.json'
    marker.write_text(json.dumps({'format': 1, 'sha256': hashlib.sha256(helper.read_bytes()).hexdigest()}))
    monkeypatch.setattr(actions.sys, 'executable', str(python))
    assert actions.helper() == helper
    helper.write_bytes(b'tampered')
    with pytest.raises(ContractError, match='invalid_mac_file_helper'):
        actions.helper()
    helper.unlink()
    helper.symlink_to(python)
    with pytest.raises(ContractError, match='invalid_mac_file_helper'):
        actions.helper()


def test_non_bundle_runtime_has_no_native_helper(monkeypatch):
    monkeypatch.setattr(actions.sys, 'executable', str(Path('/usr/bin/python3')))
    assert actions.helper() is None


@pytest.mark.parametrize('failure', [OSError('native service unavailable'), subprocess.TimeoutExpired('helper', 20)])
def test_native_service_failure_preserves_source(tmp_path, monkeypatch, failure):
    source = tmp_path / 'Forkit Session Receipt.app'
    source.mkdir()
    monkeypatch.setattr(actions, 'helper', lambda: tmp_path / 'controlled-helper')

    def failed_run(*args, **kwargs):
        raise failure

    monkeypatch.setattr(actions.subprocess, 'run', failed_run)
    with pytest.raises(ContractError, match='^mac_native_trash_failed$'):
        actions.trash(source)
    assert source.is_dir()


def test_native_service_malformed_success_does_not_complete(tmp_path, monkeypatch):
    source = tmp_path / 'Forkit Session Receipt.app'
    source.mkdir()
    monkeypatch.setattr(actions, 'helper', lambda: tmp_path / 'controlled-helper')
    monkeypatch.setattr(actions.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess([], 0, b'[]'))
    with pytest.raises(ContractError, match='^mac_native_trash_failed$'):
        actions.trash(source)
    assert source.is_dir()
