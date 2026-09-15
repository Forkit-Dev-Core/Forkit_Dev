"""Real-project shortcuts and non-mutating local setup diagnostics."""
from __future__ import annotations

import json
import socket
import subprocess
from unittest.mock import patch

import pytest

from forkit_radar.cli import main
from forkit_radar.onboarding import diagnose
from forkit_radar.sessions.storage import SessionStore


def project(root, name):
    p = root / name
    p.mkdir()
    subprocess.run(['/usr/bin/git', 'init', '-q', str(p)], check=True)
    (p / 'app.py').write_text('value = 1\n')
    return p


def test_shortcuts_finish_only_selected_project(tmp_path, capsys):
    a, b = project(tmp_path, 'a'), project(tmp_path, 'b')
    root = tmp_path / 'private'
    for p in (a, b):
        assert main(['start', '--tool', 'cursor', '--project', str(p), '--store', str(root)]) == 0
    (a / 'app.py').write_text('value = 2\n')
    assert main(['stop', '--project', str(a), '--store', str(root), '--json']) == 0
    store = SessionStore(root)
    assert len(store.active()) == 1 and store.active_in(b) is not None
    assert store.active_in(a) is None
    receipt = store.receipt()
    assert len(receipt.file_changes) == 1 and receipt.tool == 'cursor'
    before = (root / 'sessions.sqlite3').read_bytes()
    assert main(['stop', '--project', str(a), '--store', str(root)]) == 2
    assert (root / 'sessions.sqlite3').read_bytes() == before
    assert 'no_active_session_in_selected_project' in capsys.readouterr().err


def test_shortcut_does_not_finish_wrapped_session(tmp_path, capsys):
    p = project(tmp_path, 'project')
    store = SessionStore(tmp_path / 'private')
    start, _ = store.start(p, tool='other', mode='wrapper')
    assert main(['stop', '--project', str(p), '--store', str(store.root)]) == 2
    assert store.active()[0].started.session_id == start.session_id
    assert 'wrapped_session' in capsys.readouterr().err


def test_replaced_or_cloned_project_not_selected(tmp_path):
    a = project(tmp_path, 'project')
    store = SessionStore(tmp_path / 'private')
    start, _ = store.start(a, tool='other')
    a.rename(tmp_path / 'moved')
    replacement = project(tmp_path, 'project')
    assert store.active_in(replacement) is None
    assert store.active_in(tmp_path / 'moved') is None
    assert store.active()[0].started.session_id == start.session_id


def test_doctor_reads_no_source_creates_no_store_and_uses_no_network(tmp_path):
    p = project(tmp_path, 'SECRET-project')
    root = tmp_path / 'PRIVATE-store'
    with patch.object(socket, 'socket', side_effect=AssertionError('network')):
        with patch('forkit_radar.sessions.inventory.capture', side_effect=AssertionError('source capture')):
            result = diagnose(p, root)
    assert result['ready'] and not root.exists()
    assert not result['network_used'] and not result['writes_performed']
    assert 'SECRET' not in json.dumps(result) and 'PRIVATE' not in json.dumps(result)
    assert 'PATH' not in json.dumps(result)  # No selected executable lookup needed.


@pytest.mark.parametrize('kind', ['outside_git', 'subdirectory', 'store_in_project', 'unsafe_store'])
def test_doctor_explains_blockers_without_changes(tmp_path, kind):
    p = project(tmp_path, 'project')
    root = tmp_path / 'private'
    if kind == 'outside_git':
        p = tmp_path
    elif kind == 'subdirectory':
        p = p / 'sub'
        p.mkdir()
    elif kind == 'store_in_project':
        root = p / 'private'
    else:
        root.mkdir(mode=0o755)
    result = diagnose(p, root)
    assert not result['ready']
    assert not (root / 'sessions.sqlite3').exists()


def test_doctor_and_welcome_cli(tmp_path, capsys):
    p = project(tmp_path, 'project')
    assert main([]) == 0
    output = capsys.readouterr().out
    assert 'start --tool cursor' in output and 'stop' in output
    assert main(['doctor', '--project', str(p), '--store', str(tmp_path / 'private'), '--json']) == 0
    assert json.loads(capsys.readouterr().out)['ready']


def test_start_prints_reusable_custom_store_command(tmp_path, capsys):
    p = project(tmp_path, 'space project')
    root = tmp_path / 'space store'
    assert main(['start', '--tool', 'other', '--project', str(p), '--store', str(root)]) == 0
    output = capsys.readouterr().out
    import shlex
    assert '--project ' + shlex.quote(str(p)) in output
    assert '--store ' + shlex.quote(str(root)) in output
