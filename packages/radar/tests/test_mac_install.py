"""Real APFS activation/recovery with small app fixtures; signing tested separately."""
import hashlib
import json
import os
import plistlib
import subprocess
import sys
from pathlib import Path

import pytest

from forkit_radar import mac_install as mac
from forkit_radar.capture import automatic as auto
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.storage import SessionStore

pytestmark = pytest.mark.skipif(sys.platform != 'darwin', reason='Darwin atomic app installation')


@pytest.fixture
def local(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir(mode=0o700)
    root = home / '.forkit-radar'
    root.mkdir(mode=0o700)
    monkeypatch.setattr(Path, 'home', lambda: home)
    monkeypatch.setenv('CODEX_HOME', str(home / '.codex'))
    monkeypatch.setenv('CLAUDE_CONFIG_DIR', str(home / '.claude'))
    monkeypatch.setattr(auto, 'detected', lambda _: {'codex'})
    monkeypatch.setattr(mac, 'signature', lambda _: None)
    return home, root


def app_at(path, version='4.3'):
    native = path / 'Contents/MacOS/Forkit'
    native.parent.mkdir(parents=True)
    native.write_bytes(b'controlled native fixture ' + version.encode())
    native.chmod(0o755)
    (path / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': mac.BUNDLE_ID,
        'CFBundleExecutable': 'Forkit', 'CFBundleVersion': version}))
    resources = path / 'Contents/Resources'
    git = resources / 'git/bin/git'
    git.parent.mkdir(parents=True)
    git.write_bytes(b'controlled Git fixture')
    runtime = resources / 'runtime'
    (runtime / 'bin').mkdir(parents=True)
    (runtime / 'bin/python3.11').write_bytes(b'controlled Python fixture')
    (runtime / 'forkit-runtime.json').write_text(json.dumps({'format': 1,
        'git_sha256': hashlib.sha256(git.read_bytes()).hexdigest()}))
    return path


def source(home, version='4.3'):
    return app_at(home / ('download-' + version) / mac.APP_NAME, version)


def test_fresh_install_offline_no_login_and_idempotency(local):
    home, root = local
    original = source(home)
    result = mac.install(root, source=original)
    app, cli = mac.paths(home)
    assert result['installed'] and app.is_dir() and cli.read_bytes() == mac.cli_bytes(app)
    assert cli.stat().st_mode & 0o111 and not (root / 'sessions.sqlite3').exists()
    before = (root / mac.RECORD).read_bytes()
    assert mac.install(root, source=original)['same_version']
    assert (root / mac.RECORD).read_bytes() == before
    assert not (root / mac.JOURNAL).exists() and not (root / 'usage-consent.json').exists()


def test_updates_and_rollback_preserve_history_and_paused_capture(local):
    home, root = local
    auto.setup(root)
    auto.setup(root, disable=True)
    (root / 'history-to-preserve').write_text('local history')
    mac.install(root, source=source(home, '4.3'))
    before = mac.record(root, home)['current']['digest']
    mac.install(root, source=source(home, '4.4'))
    record = mac.record(root, home)
    assert record['previous']['digest'] == before
    assert not auto.state(root)['agents']['codex']['enabled']
    mac.rollback(root)
    assert mac.record(root, home)['current']['digest'] == before
    assert (root / 'history-to-preserve').read_text() == 'local history'
    assert not auto.state(root)['agents']['codex']['enabled']


def test_third_update_retires_old_backup_and_remove_preserves_history(local):
    home, root = local
    for version in ['4.3', '4.4', '4.5']:
        mac.install(root, source=source(home, version))
    app, cli = mac.paths(home)
    assert len(list(app.parent.glob('.Forkit Previous *.app'))) == 1
    assert len(list((home / '.Trash').glob('*.app'))) == 1
    (root / 'history-to-preserve').write_text('private receipt')
    auto.setup(root)
    mac.remove(root)
    assert not app.exists() and not cli.exists()
    assert not list(app.parent.glob('.Forkit Previous *.app'))
    assert len(list((home / '.Trash').glob('*.app'))) == 3
    assert (root / 'history-to-preserve').read_text() == 'private receipt'
    assert not (root / mac.RECORD).exists() and not auto.state(root)['agents']['codex']['enabled']


def test_trash_denial_keeps_updates_and_backups_and_does_not_disable_capture(local, monkeypatch):
    home, root = local
    original = mac.private_parents
    def denied_trash(path):
        if path == home / '.Trash':
            raise PermissionError('controlled macOS Trash denial')
        return original(path)
    monkeypatch.setattr(mac, 'private_parents', denied_trash)
    for version in ['4.3', '4.4', '4.5', '4.6']:
        assert mac.install(root, source=source(home, version))['installed']
    record = mac.record(root, home)
    assert len(record['retired']) == 2
    assert all(Path(item['path']).exists() for item in record['retired'])
    assert mac.status(root)['cleanup_pending']
    auto.setup(root)
    before = (root / auto.STATE).read_bytes()
    with pytest.raises(ContractError, match='mac_trash_access_unavailable'):
        mac.remove(root)
    assert (root / auto.STATE).read_bytes() == before
    assert mac.paths(home)[0].exists() and mac.paths(home)[1].exists()
    assert not (root / mac.REMOVAL).exists()


def test_native_trash_retries_after_move_without_reading_trash(local, monkeypatch):
    home, root = local
    mac.install(root, source=source(home))
    auto.setup(root)
    monkeypatch.setattr(mac.mac_file_actions, 'helper', lambda: Path('/reviewed/helper'))
    moved = home / 'controlled-system-trash'
    moved.mkdir()
    def native_trash(path):
        path.rename(moved / path.name)
        raise SystemExit('interrupted after native move')
    monkeypatch.setattr(mac.mac_file_actions, 'trash', native_trash)
    original = mac.private_parents
    def no_direct_trash(path):
        assert path != home / '.Trash'
        return original(path)
    monkeypatch.setattr(mac, 'private_parents', no_direct_trash)
    with pytest.raises(SystemExit):
        mac.remove(root)
    assert not mac.paths(home)[0].exists()
    assert mac.remove(root)['removed']
    assert not (root / mac.REMOVAL).exists()
    assert not auto.state(root)['agents']['codex']['enabled']


def test_retained_backups_switch_to_native_trash_before_moving(local, monkeypatch):
    home, root = local
    mac.install(root, source=source(home, '4.3'))
    mac.install(root, source=source(home, '4.4'))
    original = mac.finish_trash
    monkeypatch.setattr(mac, 'finish_trash', lambda *_: (_ for _ in ()).throw(PermissionError()))
    mac.install(root, source=source(home, '4.5'))
    monkeypatch.setattr(mac, 'finish_trash', original)
    monkeypatch.setattr(mac.mac_file_actions, 'helper', lambda: Path('/reviewed/helper'))
    def native_trash(path):
        pending = mac.record(root, home)['retired'][0]
        assert pending['native'] is True and pending['path'] == str(path)
        path.rename(home / 'retired-in-native-trash.app')
    monkeypatch.setattr(mac.mac_file_actions, 'trash', native_trash)
    mac.retire(root, home)
    assert not mac.record(root, home)['retired']


def test_foreign_app_and_command_are_never_overwritten(local):
    home, root = local
    app, cli = mac.paths(home)
    app.mkdir(parents=True)
    marker = app / 'not-forkit.txt'
    marker.write_text('keep')
    original = source(home)
    with pytest.raises((OSError, ValueError)):
        mac.install(root, source=original)
    assert marker.read_text() == 'keep'
    # Remove only this controlled foreign fixture to exercise independent CLI preservation.
    marker.unlink()
    app.rmdir()
    cli.parent.mkdir(parents=True, exist_ok=True)
    cli.write_text('#!/bin/sh\necho user command\n')
    before = cli.read_bytes()
    assert not mac.install(root, source=original)['command_installed']
    mac.install(root, source=source(home, '4.4'))
    mac.rollback(root)
    mac.remove(root)
    assert cli.read_bytes() == before


def test_foreign_linked_command_does_not_block_standalone_app(local):
    home, root = local
    _, cli = mac.paths(home)
    cli.parent.mkdir(parents=True)
    foreign = home / 'my-own-command'
    foreign.write_text('keep this command')
    cli.symlink_to(foreign)
    assert not mac.install(root, source=source(home))['command_installed']
    mac.remove(root)
    assert cli.is_symlink() and foreign.read_text() == 'keep this command'


def test_tampered_backup_is_not_removed_or_used_to_disable_hooks(local):
    home, root = local
    mac.install(root, source=source(home, '4.3'))
    mac.install(root, source=source(home, '4.4'))
    auto.setup(root)
    config = home / '.codex/hooks.json'
    before = config.read_bytes()
    backup = Path(mac.record(root, home)['previous']['path'])
    (backup / 'Contents/MacOS/Forkit').write_bytes(b'changed by another writer')
    with pytest.raises(ContractError, match='mac_backup_changed'):
        mac.remove(root)
    assert config.read_bytes() == before and auto.state(root)['agents']['codex']['enabled']
    assert mac.paths(home)[0].exists() and backup.exists()


@pytest.mark.parametrize('point', ['before_swap', 'after_swap', 'after_cli'])
def test_interrupted_install_is_recoverable_at_real_activation_boundary(local, monkeypatch, point):
    home, root = local
    original = source(home)
    exchange, command = mac.exchange, mac.command_write
    def stop_swap(first, second, *, swap):
        if point == 'before_swap':
            raise SystemExit('controlled interruption')
        exchange(first, second, swap=swap)
        raise SystemExit('controlled interruption')
    def stop_command(path, raw, *, expected):
        command(path, raw, expected=expected)
        raise SystemExit('controlled interruption')
    if point == 'after_cli':
        monkeypatch.setattr(mac, 'command_write', stop_command)
    else:
        monkeypatch.setattr(mac, 'exchange', stop_swap)
    with pytest.raises(SystemExit):
        mac.install(root, source=original)
    assert (root / mac.JOURNAL).exists()
    monkeypatch.setattr(mac, 'exchange', exchange)
    monkeypatch.setattr(mac, 'command_write', command)
    mac.recover(root, home)
    assert not (root / mac.JOURNAL).exists()
    if point == 'before_swap':
        assert not mac.paths(home)[0].exists()
        mac.install(root, source=original)
    assert mac.paths(home)[1].read_bytes() == mac.cli_bytes(mac.paths(home)[0])


def test_remove_retries_after_app_moved_but_record_not_cleared(local, monkeypatch):
    home, root = local
    mac.install(root, source=source(home))
    writer = mac.write_record
    def crash_before_record_clear(target, value):
        if value is None:
            raise SystemExit('controlled interruption')
        writer(target, value)
    monkeypatch.setattr(mac, 'write_record', crash_before_record_clear)
    with pytest.raises(SystemExit):
        mac.remove(root)
    assert (root / mac.REMOVAL).exists() and not mac.paths(home)[0].exists()
    monkeypatch.setattr(mac, 'write_record', writer)
    assert mac.remove(root)['removed']
    assert not (root / mac.RECORD).exists() and not (root / mac.REMOVAL).exists()
    assert mac.install(root, source=home / 'download-4.3' / mac.APP_NAME)['installed']


def test_modified_owned_hooks_stop_removal_and_keep_executable(local):
    home, root = local
    mac.install(root, source=source(home))
    auto.setup(root)
    config = home / '.codex/hooks.json'
    config.write_text('{"hooks":{}}')
    with pytest.raises(ContractError, match='hooks_needs_attention'):
        mac.remove(root)
    assert mac.paths(home)[0].exists()
    assert config.read_text() == '{"hooks":{}}'


def test_active_coding_session_blocks_install_before_any_app_change(local):
    home, root = local
    project = home / 'project'
    project.mkdir()
    subprocess.run(['/usr/bin/git', 'init', '-q', str(project)], check=True)
    (project / 'app.py').write_text('value=1\n')
    SessionStore(root).start(project, tool='codex', mode='manual')
    with pytest.raises(ContractError, match='finish_sessions_before_mac_update'):
        mac.install(root, source=source(home))
    assert not mac.paths(home)[0].exists() and len(SessionStore(root).active()) == 1


def test_new_session_cannot_enter_after_final_update_check(local, monkeypatch):
    home, root = local
    mac.install(root, source=source(home, '4.3'))
    project = home / 'project'
    project.mkdir()
    subprocess.run(['/usr/bin/git', 'init', '-q', str(project)], check=True)
    (project / 'app.py').write_text('before\n')
    original = mac.exchange
    attempts = []

    def interleaved(first, second, *, swap):
        with pytest.raises(ContractError, match='local_capture_busy_retry'):
            SessionStore(root).start(project, tool='codex')
        attempts.append('refused')
        return original(first, second, swap=swap)

    monkeypatch.setattr(mac, 'exchange', interleaved)
    assert mac.install(root, source=source(home, '4.4'))['installed']
    assert attempts == ['refused'] and not SessionStore(root).active()
    assert mac.record(root, home)['current']['version'] == '4.4'


def test_drag_and_drop_adoption_creates_managed_install(local):
    home, root = local
    app, cli = mac.paths(home)
    app_at(app)
    assert mac.install(root, source=app)['adopted']
    assert mac.status(root)['managed'] and cli.read_bytes() == mac.cli_bytes(app)


def test_opening_an_installed_app_during_capture_is_not_an_update(local, monkeypatch):
    home, root = local
    original = source(home)
    mac.install(root, source=original)
    monkeypatch.setattr(mac, 'no_active', lambda _: pytest.fail('ordinary opening must not require ending a session'))
    assert mac.install(root, source=mac.paths(home)[0])['same_location']


def test_legacy_upgrade_and_rollback_restore_owned_command_and_hook_target(local):
    home, root = local
    app, cli = mac.paths(home)
    executable = app / 'Contents/MacOS/Forkit'
    executable.parent.mkdir(parents=True)
    import shlex
    python = home / '.local/share/forkit-radar/venv/bin/python'
    executable.write_text('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' -I -m forkit_radar open\n')
    executable.chmod(0o755)
    (app / 'Contents/Info.plist').write_bytes(plistlib.dumps({'CFBundleIdentifier': 'dev.forkit.sessionreceipt.local', 'CFBundleVersion': '4'}))
    cli.parent.mkdir(parents=True)
    cli.write_bytes(mac.legacy_cli(home))
    cli.chmod(0o755)
    before = mac.app_tree(app)[0]
    auto.setup(root, executable=python)
    candidate = source(home)
    mac.install(root, source=candidate)
    assert 'Contents/Resources/runtime/bin/python3.11' in (home / '.codex/hooks.json').read_text()
    mac.rollback(root)
    assert mac.app_tree(app)[0] == before and cli.read_bytes() == mac.legacy_cli(home)
    assert str(python) in (home / '.codex/hooks.json').read_text()
    assert mac.install(root, source=candidate)['installed']


@pytest.mark.parametrize('mutation', ['external_symlink', 'hardlink', 'other_writer', 'changed_git'])
def test_changed_or_unsafe_app_is_refused(local, mutation):
    home, root = local
    candidate = source(home)
    executable = candidate / 'Contents/MacOS/Forkit'
    if mutation == 'external_symlink':
        (candidate / 'external').symlink_to(home)
    elif mutation == 'hardlink':
        os.link(executable, home / 'linked-executable')
    elif mutation == 'other_writer':
        executable.chmod(0o777)
    else:
        (candidate / 'Contents/Resources/git/bin/git').write_bytes(b'changed')
    with pytest.raises((OSError, ValueError)):
        mac.install(root, source=candidate)
    assert not mac.paths(home)[0].exists()
