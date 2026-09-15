"""User config preservation, real Git receipts and install-once scope boundaries."""
import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from forkit_radar.capture import automatic as auto
from forkit_radar.capture import setup_files
from forkit_radar.jsonio import ContractError
from forkit_radar.local_app import capture_panel, refresh
from forkit_radar.sessions.storage import SessionStore


@pytest.fixture
def local(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setenv('CODEX_HOME', str(home / '.codex'))
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(home / '.claude'))
    monkeypatch.setattr(auto, 'detected', lambda _home: {'codex'})
    return home, home / '.forkit-radar'


def project(home, name='project'):
    path = home / name
    path.mkdir(parents=True)
    subprocess.run(['/usr/bin/git', 'init', '-q', str(path)], check=True)
    (path / 'app.py').write_text('value = 1\n')
    return path


def payload(path, event, *, agent='codex', identity='external-1'):
    data = {'cwd': str(path), 'hook_event_name': event, 'session_id': identity,
            'source': 'startup', 'transcript_path': '/never/read/private-chat.jsonl',
            'prompt': 'DO_NOT_RETAIN_THIS_PROMPT'}
    if agent == 'cursor':
        data.update(workspace_roots=[str(path)], is_background_agent=False)
    return auto.encode(data)


def test_install_once_idempotent_and_restore_exact_existing_bytes(local):
    home, root = local
    path = home / '.codex/hooks.json'
    path.parent.mkdir()
    before = b'{"other_setting": "keep", "hooks":{"SessionStart":[{"hooks":[{"type":"command","command":"echo original"}]}]}}\n'
    path.write_bytes(before)
    path.chmod(0o600)
    path.parent.chmod(0o700)
    assert auto.setup(root)['ready']
    after = path.read_bytes()
    assert json.loads(after)['other_setting'] == 'keep'
    assert len(json.loads(after)['hooks']['SessionStart']) == 2
    assert auto.setup(root)['ready'] and path.read_bytes() == after
    assert len(list(root.glob('setup-backup-*'))) == 1
    assert not (root / 'sessions.sqlite3').exists()
    assert auto.setup(root, disable=True)['ready']
    assert path.read_bytes() == before
    assert not auto.state(root)['agents']['codex']['enabled']
    assert auto.setup(root, disable=True)['ready']
    assert path.read_bytes() == before


def test_upgrade_and_interrupted_setup_restore_original_config(local, monkeypatch):
    home, root = local
    path = home / '.codex/hooks.json'
    path.parent.mkdir()
    before = b'{"keep":"exact bytes"}\n'
    path.write_bytes(before)
    path.chmod(0o600)
    path.parent.chmod(0o700)
    auto.setup(root)
    monkeypatch.setattr(auto.sys, 'executable', '/new/python with space')
    assert auto.setup(root)['ready']
    assert 'new/python' in path.read_text()
    # A crash after config publication but before activation is recoverable.
    current = auto.state(root)
    current['agents']['codex'].update(enabled=False, phase='pending')
    auto.save(root, current)
    assert auto.setup(root)['ready']
    auto.setup(root, disable=True)
    assert path.read_bytes() == before


def test_directory_alias_keeps_hook_review_generation_and_venv(local, monkeypatch):
    home, root = local
    runtime = home / 'runtime'
    (runtime / 'bin').mkdir(parents=True)
    python = runtime / 'bin/python'
    python.symlink_to(auto.sys.executable)
    alias = home / 'runtime-alias'
    alias.symlink_to(runtime, target_is_directory=True)
    monkeypatch.setattr(auto.sys, 'executable', str(python))
    assert auto.setup(root)['ready']
    before = (root / auto.STATE).read_bytes()
    monkeypatch.setattr(auto.sys, 'executable', str(alias / 'bin/python'))
    assert auto.setup(root)['ready']
    assert (root / auto.STATE).read_bytes() == before
    command = json.loads(before)['agents']['codex']['groups']['SessionEnd'][0]['hooks'][0]['command']
    assert str(python) in command


def test_disable_preserves_unrelated_later_edits(local):
    home, root = local
    auto.setup(root)
    path = home / '.codex/hooks.json'
    changed = json.loads(path.read_bytes())
    changed['other_setting'] = 'user added later'
    changed['hooks']['Stop'] = [{'hooks': [{'type': 'command', 'command': 'echo keep'}]}]
    path.write_bytes(auto.encode(changed))
    assert auto.setup(root, disable=True)['ready']
    actual = json.loads(path.read_bytes())
    assert actual['other_setting'] == 'user added later'
    assert set(actual['hooks']) == {'Stop'}


def test_disable_stops_callback_even_if_user_edited_owned_config(local):
    home, root = local
    auto.setup(root)
    path = home / '.codex/hooks.json'
    path.write_bytes(b'{"hooks": {}}')
    assert not auto.setup(root, disable=True)['ready']
    p = project(home)
    auto.automatic_receive('codex', root, payload(p, 'SessionStart'))
    assert not (root / 'sessions.sqlite3').exists()


@pytest.mark.parametrize('kind', ['malformed', 'duplicate_keys', 'array_hooks', 'symlink', 'disabled_by_user', 'oversized', 'group_writable'])
def test_bad_config_never_overwritten(local, kind):
    home, root = local
    path = home / '.codex/hooks.json'
    path.parent.mkdir()
    raw = {'malformed': b'{', 'duplicate_keys': b'{"hooks":{},"hooks":{}}',
           'array_hooks': b'{"hooks":[]}', 'disabled_by_user': b'{"disableAllHooks":true}',
           'oversized': b' ' * 65537}.get(kind, b'{"keep":"original"}')
    path.write_bytes(raw)
    if kind == 'symlink':
        target = home / 'real-config'
        path.rename(target)
        path.symlink_to(target)
    if kind == 'group_writable':
        path.chmod(0o666)
    assert not auto.setup(root)['ready']
    assert path.read_bytes() == raw


def test_no_tool_detection_or_status_writes_nothing(local, monkeypatch):
    home, root = local
    monkeypatch.setattr(auto, 'detected', lambda _: set())
    assert auto.setup(root)['agents'] == []
    assert not root.exists()
    result = auto.setup(root, inspect=True)
    assert len(result['agents']) == 3 and not result['ready']
    assert not root.exists() and not (home / '.codex').exists()


@pytest.mark.parametrize('agent,start,end', [('codex','SessionStart','SessionEnd'),('claude-code','SessionStart','SessionEnd'),('cursor','sessionStart','sessionEnd')])
def test_global_hooks_find_projects_without_per_project_setup(local, monkeypatch, agent, start, end):
    home, root = local
    auto.setup(root, agents=[agent])
    p = project(home)
    sub = p / 'src'
    sub.mkdir()
    monkeypatch.setattr(socket, 'socket', lambda *_a, **_k: pytest.fail('network attempted'))
    auto.automatic_receive(agent, root, payload(sub, start, agent=agent))
    auto.automatic_receive(agent, root, payload(sub, start, agent=agent))
    (p / 'app.py').write_text('value = 2\n')
    auto.automatic_receive(agent, root, payload(sub, end, agent=agent))
    auto.automatic_receive(agent, root, payload(sub, end, agent=agent))
    store = SessionStore(root)
    assert len(store.history()) == 1 and not store.active()
    receipt = store.receipt()
    assert len(receipt.file_changes) == 1 and receipt.tool_basis == 'hook_reported'
    assert receipt.passport_id is None  # No invented Passport or creator metadata.
    assert receipt.comparison == ('partial' if agent == 'cursor' else 'complete')
    view = refresh(root)
    assert 'Hook-reported tool' in view.read_text()
    from forkit_radar.sessions.cards import encode
    from forkit_radar.sessions.cards import project as share_card
    for extension in ('.html', '.svg', '.json'):
        assert encode(share_card(receipt), extension)
    for f in root.iterdir():
        if f.is_file():
            assert b'DO_NOT_RETAIN_THIS_PROMPT' not in f.read_bytes()
            assert b'private-chat.jsonl' not in f.read_bytes()
            assert b'external-1' not in f.read_bytes()
    assert not (p / '.codex').exists() and not (p / '.cursor').exists()


def test_independent_projects_and_foreign_session_boundary(local):
    home, root = local
    auto.setup(root)
    a, b = project(home, 'a'), project(home, 'b')
    auto.automatic_receive('codex', root, payload(a, 'SessionStart', identity='a'))
    auto.automatic_receive('codex', root, payload(b, 'SessionStart', identity='b'))
    with pytest.raises(ContractError):
        auto.automatic_receive('codex', root, payload(a, 'SessionEnd', identity='b'))
    auto.automatic_receive('codex', root, payload(b, 'SessionEnd', identity='b'))
    assert len(SessionStore(root).active()) == 1
    auto.automatic_receive('codex', root, payload(a, 'SessionEnd', identity='a'))
    assert len(SessionStore(root).history()) == 2


def test_no_home_scan_parent_repository_walk_or_symlink_escape(local):
    home, root = local
    auto.setup(root)
    subprocess.run(['/usr/bin/git', 'init', '-q', str(home)], check=True)
    folder = home / 'Downloads/folder'
    folder.mkdir(parents=True)
    auto.automatic_receive('codex', root, payload(folder, 'SessionStart'))
    auto.automatic_receive('codex', root, payload(home, 'SessionStart'))
    assert not (root / 'sessions.sqlite3').exists()
    p = project(home, 'real-project')
    alias = home / 'alias'
    alias.symlink_to(p)
    with pytest.raises((OSError, ValueError)):
        auto.automatic_receive('codex', root, payload(alias, 'SessionStart'))
    assert not (root / 'sessions.sqlite3').exists()


def test_new_config_disabled_removed_and_history_preserved(local):
    home, root = local
    p = project(home)
    auto.setup(root)
    auto.automatic_receive('codex', root, payload(p, 'SessionStart'))
    auto.automatic_receive('codex', root, payload(p, 'SessionEnd'))
    before = (root / 'sessions.sqlite3').read_bytes()
    auto.setup(root, disable=True)
    assert not (home / '.codex/hooks.json').exists()
    assert (root / 'sessions.sqlite3').read_bytes() == before
    auto.setup(root)
    assert auto.state(root)['agents']['codex']['enabled']


def test_config_change_check_and_private_backup(local):
    home, root = local
    setup_files.private_directory(root)
    path = root / 'config.json'
    path.write_bytes(b'other writer')
    with pytest.raises(ContractError):
        setup_files.replace(path, b'ours', expected=b'before')
    assert path.read_bytes() == b'other writer'
    with setup_files.locked(root):
        with pytest.raises(ContractError):
            with setup_files.locked(root):
                pytest.fail('overlapping setup acquired')


def test_open_history_reuses_private_view_without_network(local, monkeypatch):
    home, root = local
    auto.setup(root)
    monkeypatch.setattr(socket, 'socket', lambda *_a, **_k: pytest.fail('network attempted'))
    p = refresh(root)
    assert 'Automatic local capture' in p.read_text()
    assert '0 saved receipts' in p.read_text()
    assert os.stat(p).st_mode & 0o777 == 0o600
    q = refresh(root)
    assert q.exists() and not p.exists()
    assert 'connect-src \'none\'' in q.read_text()


def test_setup_change_cannot_reuse_previous_callback_as_readiness(local, monkeypatch):
    home, root = local
    auto.setup(root)
    assert 'data-capture-state="setup"' in capture_panel(root)
    p = project(home)
    auto.automatic_receive('codex', root, payload(p, 'SessionStart'))
    auto.automatic_receive('codex', root, payload(p, 'SessionEnd'))
    assert 'data-capture-state="observed"' in capture_panel(root)
    old = auto.state(root)['agents']['codex']['generation']
    monkeypatch.setattr(auto.sys, 'executable', '/new/reviewed/python')
    auto.setup(root)
    assert auto.state(root)['agents']['codex']['generation'] != old
    assert 'data-capture-state="setup"' in capture_panel(root)


def test_damaged_capture_status_does_not_hide_saved_receipts(local):
    home, root = local
    auto.setup(root)
    p = project(home)
    auto.automatic_receive('codex', root, payload(p, 'SessionStart'))
    auto.automatic_receive('codex', root, payload(p, 'SessionEnd'))
    (root / 'capture-status-codex.json').write_bytes(b'{')
    assert '1 saved receipt' in refresh(root).read_text()
    (root / auto.STATE).write_bytes(b'{')
    page = refresh(root).read_text()
    assert '1 saved receipt' in page and 'data-capture-state="attention"' in page


def test_in_flight_old_callback_does_not_confirm_replacement_setup(local, monkeypatch):
    home, root = local
    auto.setup(root)
    original = auto.state(root)['agents']['codex']['generation']
    p = project(home)

    def replacement(_args, _raw):
        current = auto.state(root)
        current['agents']['codex']['generation'] = 'replacement'
        auto.save(root, current)
        return 'capture_started'

    monkeypatch.setattr(auto, 'receive', replacement)
    auto.automatic_receive('codex', root, payload(p, 'SessionStart'))
    event = json.loads((root / 'capture-status-codex.json').read_bytes())
    assert event['generation'] == original
    assert 'data-capture-state="setup"' in capture_panel(root)


def test_interrupted_setup_is_attention_not_user_paused(local):
    _home, root = local
    auto.setup(root)
    for phase in ('pending', 'disabling'):
        current = auto.state(root)
        current['agents']['codex'].update(enabled=False, phase=phase)
        auto.save(root, current)
        status = auto.setup(root, inspect=True)
        assert status['agents'][0]['state'] == 'needs_attention' and not status['ready']
        assert 'data-capture-state="attention"' in capture_panel(root)


def test_pause_cannot_cross_an_inflight_callback(local, monkeypatch):
    home, root = local
    auto.setup(root)
    p = project(home)
    receive = auto.receive

    def pause_during_callback(args, raw):
        with pytest.raises(ContractError, match='local_capture_busy_retry'):
            auto.setup(root, disable=True)
        assert auto.state(root)['agents']['codex']['enabled']
        return receive(args, raw)

    monkeypatch.setattr(auto, 'receive', pause_during_callback)
    auto.automatic_receive('codex', root, payload(p, 'SessionStart'))
    assert len(SessionStore(root).active()) == 1
    assert auto.setup(root, disable=True)['ready']
    # Pause intentionally keeps this baseline for explicit recovery.
    auto.automatic_receive('codex', root, payload(p, 'SessionEnd'))
    assert len(SessionStore(root).active()) == 1 and not SessionStore(root).history()
