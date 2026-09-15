"""Guarded per-user Mac installation. Local files only; no downloader/updater service.

The new bundle is staged and verified before an atomic directory exchange. A small
journal makes interruption before/after that exchange distinguishable. It is not
a defense against a hostile same-user process. Coding must stop during updates.
"""
from __future__ import annotations

import base64
import ctypes
import hashlib
import json
import os
import plistlib
import re
import shlex
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import psutil

from . import mac_file_actions
from .capture import setup_files as files
from .capture.automatic import setup, state
from .discovery.safeio import directory
from .jsonio import ContractError, load_json
from .lifecycle import maintenance
from .sessions.storage import SessionStore

APP_NAME = 'Forkit Session Receipt.app'
BUNDLE_ID = 'dev.forkit.session-receipt'
RECORD = 'mac-installation.json'
JOURNAL = 'mac-install-transaction.json'
REMOVAL = 'mac-removal.json'
MAX_APP_BYTES = 536_870_912


def encode(value):
    return (json.dumps(value, sort_keys=True, separators=(',', ':')) + '\n').encode()


def private_parents(path):
    """Create only the missing per-user directories, rejecting symlink parents."""
    missing = []
    existing = path
    while not existing.exists() and not existing.is_symlink():
        missing.append(existing)
        existing = existing.parent
    with directory(existing):
        pass
    for p in reversed(missing):
        p.mkdir(mode=0o700)
    with directory(path) as fd:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ContractError('unsafe_mac_install_directory')


def paths(home):
    return home / 'Applications' / APP_NAME, home / '.local/bin/forkit-radar'


def app_tree(app):
    """Bound and fingerprint all installed bytes; allow only internal symlinks."""
    with directory(app) as fd:
        root_info = os.fstat(fd)
        if root_info.st_uid != os.geteuid() or root_info.st_mode & 0o022:
            raise ContractError('unsafe_mac_app')
    digest = hashlib.sha256()
    total = count = 0
    for parent, directories, names in os.walk(app, followlinks=False):
        directories.sort()
        for name in sorted([*directories, *names]):
            path = Path(parent) / name
            info = path.lstat()
            count += 1
            if count > 10_000 or info.st_uid != os.geteuid():
                raise ContractError('unsafe_mac_app')
            relative = path.relative_to(app).as_posix()
            if stat.S_ISLNK(info.st_mode):
                target = os.readlink(path)
                if os.path.isabs(target) or not path.resolve(strict=True).is_relative_to(app):
                    raise ContractError('external_mac_app_link')
                item = [relative, 'link', target]
            elif stat.S_ISDIR(info.st_mode):
                if info.st_mode & 0o022:
                    raise ContractError('writable_mac_app')
                item = [relative, 'directory', stat.S_IMODE(info.st_mode)]
            elif stat.S_ISREG(info.st_mode):
                if info.st_nlink != 1 or info.st_mode & 0o022:
                    raise ContractError('unsafe_mac_app_file')
                total += info.st_size
                if total > MAX_APP_BYTES:
                    raise ContractError('mac_app_too_large')
                with path.open('rb') as source:
                    value = hashlib.file_digest(source, 'sha256').hexdigest()
                after = path.lstat()
                if (info.st_ino, info.st_size, info.st_mtime_ns) != (after.st_ino, after.st_size, after.st_mtime_ns):
                    raise ContractError('mac_app_changed')
                item = [relative, 'file', stat.S_IMODE(info.st_mode), value]
            else:
                raise ContractError('unsafe_mac_app_file')
            digest.update(encode(item))
    return digest.hexdigest(), total


def signature(app):
    # Ad-hoc builds are valid only for local development. Public trust still
    # requires Developer ID and notarization; this check never bypasses Gatekeeper.
    subprocess.run(['/usr/bin/codesign', '--verify', '--strict', '--deep', str(app)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        check=True, timeout=30)


def checked_app(app):
    app = app.absolute()
    digest, size = app_tree(app)
    info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
    if info.get('CFBundleIdentifier') != BUNDLE_ID or info.get('CFBundleExecutable') != 'Forkit':
        raise ContractError('not_a_forkit_mac_app')
    version = info.get('CFBundleVersion')
    if not isinstance(version, str) or not re.fullmatch(r'[0-9]{1,6}(?:\.[0-9]{1,6}){0,2}', version):
        raise ContractError('invalid_mac_app_version')
    marker = app / 'Contents/Resources/runtime/forkit-runtime.json'
    data = load_json(marker.read_bytes())
    git = app / 'Contents/Resources/git/bin/git'
    if set(data) != {'format', 'git_sha256'} or data['format'] != 1 or hashlib.sha256(git.read_bytes()).hexdigest() != data['git_sha256']:
        raise ContractError('invalid_mac_runtime')
    signature(app)
    return {'digest': digest, 'bytes': size, 'version': version, 'kind': 'native'}


def source_app():
    executable = Path(sys.executable).resolve(strict=True)
    if len(executable.parents) < 5:
        raise ContractError('bundled_mac_runtime_required')
    app = executable.parents[4]
    if executable != app / 'Contents/Resources/runtime/bin/python3.11':
        raise ContractError('bundled_mac_runtime_required')
    return app


def legacy_app(app, home):
    """Recognize the exact earlier Forkit launcher, not merely its bundle ID."""
    from .discovery.safeio import read_metadata
    python = home / '.local/share/forkit-radar/venv/bin/python'
    script = ('#!/bin/sh\nexec ' + shlex.quote(str(python)) + ' -I -m forkit_radar open\n').encode()
    if read_metadata(app / 'Contents/MacOS/Forkit') != script:
        raise ContractError('existing_mac_app_not_owned')
    info = plistlib.loads(read_metadata(app / 'Contents/Info.plist'))
    if info.get('CFBundleIdentifier') != 'dev.forkit.sessionreceipt.local' or info.get('CFBundleVersion') != '4':
        raise ContractError('existing_mac_app_not_owned')
    actual = {str(p.relative_to(app)) for p in app.rglob('*') if p.is_file() or p.is_symlink()}
    if actual != {'Contents/Info.plist', 'Contents/MacOS/Forkit'}:
        raise ContractError('existing_mac_app_not_owned')
    digest, size = app_tree(app)
    return {'digest': digest, 'bytes': size, 'version': '4', 'kind': 'legacy'}


def cli_bytes(app):
    python = app / 'Contents/Resources/runtime/bin/python3.11'
    return ('#!/bin/sh\n# Forkit local Mac command\nexec ' + shlex.quote(str(python)) + ' -I -B -m forkit_radar "$@"\n').encode()


def legacy_cli(home):
    python = home / '.local/share/forkit-radar/venv/bin/python'
    return ('#!/bin/sh\n# Forkit local OSS launcher\nexec ' + shlex.quote(str(python)) + ' -I -m forkit_radar.cli "$@"\n').encode()


def command_choice(home):
    app, cli = paths(home)
    try:
        private_parents(cli.parent)
        if cli.is_symlink() or (cli.exists() and cli.stat().st_size > 4096):
            return None, False
        raw = files.read(cli)
    except (OSError, ValueError):
        # A custom/linked command directory must not block the standalone app.
        return None, False
    owned = raw is None or raw in {cli_bytes(app), legacy_cli(home)}
    return (raw, True) if owned else (None, False)


def record(root, home):
    raw = files.read(root / RECORD, private=True)
    data = load_json(raw) if raw else None
    if data is not None:
        app, _ = paths(home)
        if set(data) != {'format', 'app', 'current', 'previous', 'cli_managed', 'retired'} or data['format'] != 1 or data['app'] != str(app):
            raise ContractError('invalid_mac_install_record')
        if type(data['cli_managed']) is not bool or type(data['retired']) is not list or len(data['retired']) > 100:
            raise ContractError('invalid_mac_install_record')
        for item in [data['current'], data['previous']]:
            if item is None:
                continue
            if set(item) != {'path', 'digest', 'bytes', 'version', 'kind', 'cli'} or not re.fullmatch(r'[0-9a-f]{64}', item['digest']):
                raise ContractError('invalid_mac_install_record')
            if item['path'] != str(app) and not re.fullmatch(r'\.Forkit Previous [0-9a-f-]{36}\.app', Path(item['path']).name):
                raise ContractError('invalid_mac_backup_path')
            if Path(item['path']).parent != app.parent:
                raise ContractError('invalid_mac_backup_path')
    return data


def write_record(root, data):
    path = root / RECORD
    files.replace(path, encode(data) if data else None, expected=files.read(path, private=True))


def no_active(root):
    if SessionStore(root).active():
        raise ContractError('finish_sessions_before_mac_update')


def no_running_app(app):
    own = {os.getpid(), os.getppid()}
    prefix = str(app) + '/Contents/'
    for process in psutil.process_iter(['pid', 'exe']):
        try:
            if process.pid not in own and (process.info['exe'] or '').startswith(prefix):
                raise ContractError('quit_installed_forkit_before_update')
        except (psutil.AccessDenied, psutil.NoSuchProcess):
            continue


def exchange(first, second, *, swap):
    """Darwin atomic directory exchange, or exclusive activation for first install."""
    library = ctypes.CDLL('/usr/lib/libSystem.B.dylib', use_errno=True)
    function = library.renamex_np
    function.argtypes = [ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint]
    function.restype = ctypes.c_int
    if function(os.fsencode(first), os.fsencode(second), 0x2 if swap else 0x4):
        raise OSError(ctypes.get_errno(), 'mac_install_atomic_move_failed')
    with directory(second.parent) as fd:
        os.fsync(fd)


def command_write(path, raw, *, expected):
    # Reuse guarded replacement, then make only the exact owned command executable.
    files.replace(path, raw, expected=expected)
    if raw is not None:
        path.chmod(0o755)


def clear_journal(root):
    path = root / JOURNAL
    files.replace(path, None, expected=files.read(path, private=True))


def refresh_owned_hooks(root, home, kind):
    enabled = [agent for agent, item in state(root)['agents'].items() if item['enabled']]
    if enabled:
        app, _ = paths(home)
        executable = (home / '.local/share/forkit-radar/venv/bin/python' if kind == 'legacy'
            else app / 'Contents/Resources/runtime/bin/python3.11')
        if not setup(root, agents=enabled, home=home, executable=executable)['ready']:
            raise ContractError('mac_capture_setup_needs_attention')


def recover(root, home):
    """Finish only a byte-matching, already activated transaction; never guess."""
    raw = files.read(root / JOURNAL, private=True)
    if not raw:
        return
    journal = load_json(raw)
    app, cli = paths(home)
    if set(journal) != {'format', 'app', 'stage', 'before', 'after', 'cli_before', 'cli_after', 'record'} or journal['format'] != 1 or journal['app'] != str(app):
        raise ContractError('mac_update_recovery_required')
    stage = Path(journal['stage'])
    if stage.parent != app.parent or not re.fullmatch(r'\.Forkit Previous [0-9a-f-]{36}\.app', stage.name):
        raise ContractError('mac_update_recovery_required')
    actual = app_tree(app)[0] if app.exists() else None
    if actual == journal['after']:
        # Validate the matching old version before retaining it as the rollback.
        if journal['before'] is not None and (not stage.exists() or app_tree(stage)[0] != journal['before']):
            raise ContractError('mac_update_recovery_required')
        before = base64.b64decode(journal['cli_before'], validate=True) if journal['cli_before'] is not None else None
        after = base64.b64decode(journal['cli_after'], validate=True) if journal['cli_after'] is not None else None
        if journal['record']['cli_managed']:
            observed = files.read(cli)
            if observed not in (before, after):
                raise ContractError('mac_command_changed')
            if before != after or observed != after:
                command_write(cli, after, expected=observed)
            elif after is not None and not cli.stat().st_mode & 0o111:
                cli.chmod(0o755)
        write_record(root, journal['record'])
        refresh_owned_hooks(root, home, journal['record']['current']['kind'])
        clear_journal(root)
    elif actual == journal['before']:
        # Activation never happened. Retire only the verified staging copy;
        # the old install/command/record are unchanged and can be retried.
        if not stage.exists() or app_tree(stage)[0] != journal['after']:
            raise ContractError('mac_update_recovery_required')
        finish_trash(trash_item(stage, journal['after'], home), home)
        clear_journal(root)
    else:
        raise ContractError('mac_update_recovery_required')


def trash_item(path, digest, home):
    item = {'path': str(path), 'digest': digest,
        'trash': str(home / '.Trash' / ('Forkit Session Receipt ' + str(uuid4()) + '.app'))}
    if mac_file_actions.helper() is not None:
        item['native'] = True
    return item


def check_trash(item, home):
    if set(item) not in ({'path', 'digest', 'trash'}, {'path', 'digest', 'trash', 'native'}) or ('native' in item and item['native'] is not True):
        raise ContractError('invalid_mac_trash_item')
    source, target = Path(item['path']), Path(item['trash'])
    app, _ = paths(home)
    if source != app and (source.parent != app.parent or not re.fullmatch(r'\.Forkit Previous [0-9a-f-]{36}\.app', source.name)):
        raise ContractError('invalid_mac_backup_path')
    if target.parent != home / '.Trash' or not re.fullmatch(r'Forkit Session Receipt [0-9a-f-]{36}\.app', target.name):
        raise ContractError('invalid_mac_trash_path')
    if source.exists() or source.is_symlink():
        if app_tree(source)[0] != item['digest']:
            raise ContractError('mac_backup_changed')
        if not item.get('native') and (target.exists() or target.is_symlink()):
            raise ContractError('mac_backup_changed')
    elif not item.get('native') and (not target.exists() or app_tree(target)[0] != item['digest']):
        raise ContractError('mac_backup_changed')
    return source, target


def finish_trash(item, home):
    source, target = check_trash(item, home)
    if source.exists():
        if item.get('native'):
            mac_file_actions.trash(source)
        else:
            private_parents(target.parent)
            exchange(source, target, swap=False)
    # A journaled native operation may have moved its source before interruption.
    # Absence proves removal from Applications, not a verified Trash destination.


def retire(root, home):
    data = record(root, home)
    if not data:
        return
    for item in list(data['retired']):
        if not item.get('native') and Path(item['path']).exists() and mac_file_actions.helper() is not None:
            item['native'] = True
            write_record(root, data)  # Persist the method before the OS moves it.
        try:
            finish_trash(item, home)
        except PermissionError:
            # macOS protects the real Trash independently of ordinary home
            # permissions. A completed update must keep its older backup here
            # rather than fail or request broad access just for cleanup.
            continue
        except ContractError as error:
            if str(error) != 'mac_native_trash_failed':
                raise
            continue
        data['retired'].remove(item)
        write_record(root, data)


def preflight_removal(items, home):
    for item in items:
        try:
            source, target = check_trash(item, home)
            if source.exists() and item.get('native'):
                if mac_file_actions.helper() is None:
                    raise ContractError('native_mac_file_helper_required')
            elif source.exists():
                private_parents(target.parent)
        except PermissionError:
            raise ContractError('mac_trash_access_unavailable') from None


def finish_removal(root, home):
    raw = files.read(root / REMOVAL, private=True)
    if not raw:
        return
    value = load_json(raw)
    app, cli = paths(home)
    if set(value) != {'format', 'app', 'items', 'cli_expected'} or value['format'] != 1 or value['app'] != str(app):
        raise ContractError('invalid_mac_removal_record')
    if not isinstance(value['items'], list) or not 1 <= len(value['items']) <= 102:
        raise ContractError('invalid_mac_removal_record')
    # Re-check owned hooks before removing a still-present executable, even on
    # a retry after a process interruption. A modified config stops removal.
    preflight_removal(value['items'], home)
    result = setup(root, disable=True, home=home)
    if any(item['state'] != 'disabled' for item in result['agents']):
        raise ContractError('remove_mac_hooks_needs_attention')
    expected = base64.b64decode(value['cli_expected'], validate=True) if value['cli_expected'] is not None else None
    if expected is not None and files.read(cli) == expected:
        command_write(cli, None, expected=expected)
    # Previous versions first; current executable moves last. All moves are
    # journaled and independently recoverable through the normal macOS Trash.
    for item in value['items']:
        finish_trash(item, home)
    write_record(root, None)
    files.replace(root / REMOVAL, None, expected=raw)


@maintenance
def install(root, *, source=None, home=None):
    home = (home or Path.home()).absolute()
    app, cli = paths(home)
    source = (source or source_app()).absolute()
    if source == app:
        return adopt(root, home)
    candidate = checked_app(source)
    no_active(root)
    no_running_app(app)
    files.private_directory(root)
    private_parents(app.parent)
    with files.locked(root / '.mac-install'):
        finish_removal(root, home)
        recover(root, home)
        retire(root, home)
        old_record = record(root, home)
        old = None
        if app.exists() or app.is_symlink():
            old = checked_app(app) if old_record and old_record['current']['kind'] == 'native' else legacy_app(app, home)
            if old_record and old['digest'] != old_record['current']['digest']:
                raise ContractError('installed_mac_app_changed')
            if old['digest'] == candidate['digest']:
                return {'installed': True, 'app': str(app), 'same_version': True}
            if old['kind'] == 'native' and tuple(map(int, candidate['version'].split('.'))) < tuple(map(int, old['version'].split('.'))):
                raise ContractError('older_mac_app_use_rollback')
        elif old_record:
            raise ContractError('installed_mac_app_missing')
        original_cli, manage_cli = command_choice(home)
        next_cli = cli_bytes(app) if manage_cli else None
        if shutil.disk_usage(app.parent).free < candidate['bytes'] + 134_217_728:
            raise ContractError('mac_install_disk_space')
        if old_record and len(old_record['retired']) >= 100:
            raise ContractError('mac_backup_cleanup_required')
        stage = app.parent / ('.Forkit Previous ' + str(uuid4()) + '.app')
        shutil.copytree(source, stage, symlinks=True)
        if checked_app(stage) != candidate:
            raise ContractError('staged_mac_app_changed')
        no_active(root)
        no_running_app(app)
        if (app_tree(app)[0] if app.exists() else None) != (old['digest'] if old else None):
            raise ContractError('installed_mac_app_changed')
        previous = {**old, 'path': str(stage), 'cli': base64.b64encode(original_cli).decode() if original_cli and manage_cli else None} if old else None
        retired = list(old_record['retired']) if old_record else []
        if old_record and old_record['previous']:
            stale = old_record['previous']
            retired.append(trash_item(Path(stale['path']), stale['digest'], home))
        next_record = {'format': 1, 'app': str(app), 'current': {**candidate, 'path': str(app),
            'cli': base64.b64encode(next_cli).decode() if next_cli else None}, 'previous': previous, 'cli_managed': manage_cli, 'retired': retired}
        journal = {'format': 1, 'app': str(app), 'stage': str(stage), 'before': old['digest'] if old else None,
            'after': candidate['digest'], 'cli_before': base64.b64encode(original_cli).decode() if original_cli and manage_cli else None,
            'cli_after': base64.b64encode(next_cli).decode() if next_cli else None, 'record': next_record}
        files.replace(root / JOURNAL, encode(journal), expected=None)
        exchange(stage, app, swap=old is not None)
        recover(root, home)
        retire(root, home)
        return {'installed': True, 'app': str(app), 'previous_version_kept': previous is not None,
            'command_installed': manage_cli, 'capture_setup_pending': True}


@maintenance
def adopt(root, home):
    """A user may drag the verified bundle into Applications before first open."""
    app, cli = paths(home)
    candidate = checked_app(app)
    files.private_directory(root)
    with files.locked(root / '.mac-install'):
        recover(root, home)
        current = record(root, home)
        if current:
            if current['current']['digest'] != candidate['digest']:
                raise ContractError('installed_mac_app_changed')
            retire(root, home)
            return {'installed': True, 'app': str(app), 'same_location': True}
        no_active(root)
        original_cli, manage_cli = command_choice(home)
        next_cli = cli_bytes(app) if manage_cli else None
        new = {'format': 1, 'app': str(app), 'current': {**candidate, 'path': str(app),
            'cli': base64.b64encode(next_cli).decode() if next_cli else None},
            'previous': None, 'retired': [], 'cli_managed': manage_cli}
        journal = {'format': 1, 'app': str(app), 'stage': str(app.parent / ('.Forkit Previous ' + str(uuid4()) + '.app')),
            'before': None, 'after': candidate['digest'],
            'cli_before': base64.b64encode(original_cli).decode() if manage_cli and original_cli else None,
            'cli_after': base64.b64encode(next_cli).decode() if next_cli else None, 'record': new}
        files.replace(root / JOURNAL, encode(journal), expected=None)
        recover(root, home)
        return {'installed': True, 'app': str(app), 'adopted': True, 'command_installed': manage_cli}


@maintenance
def repair(root, *, home=None):
    home = (home or Path.home()).absolute()
    files.private_directory(root)
    with files.locked(root / '.mac-install'):
        finish_removal(root, home)
        recover(root, home)
        retire(root, home)
    return status(root, home=home)


@maintenance
def rollback(root, *, home=None):
    home = (home or Path.home()).absolute()
    app, cli = paths(home)
    no_active(root)
    no_running_app(app)
    with files.locked(root / '.mac-install'):
        recover(root, home)
        current = record(root, home)
        if not current or not current['previous']:
            raise ContractError('no_previous_mac_app')
        previous = current['previous']
        stage = Path(previous['path'])
        if app_tree(app)[0] != current['current']['digest'] or app_tree(stage)[0] != previous['digest']:
            raise ContractError('mac_backup_changed')
        next_record = {**current, 'current': {**previous, 'path': str(app)},
            'previous': {**current['current'], 'path': str(stage)}}
        before = files.read(cli) if current['cli_managed'] else None
        expected = base64.b64decode(current['current']['cli'], validate=True) if current['current']['cli'] else None
        if current['cli_managed'] and before != expected:
            raise ContractError('mac_command_changed')
        journal = {'format': 1, 'app': str(app), 'stage': str(stage), 'before': current['current']['digest'],
            'after': previous['digest'], 'cli_before': current['current']['cli'], 'cli_after': previous['cli'], 'record': next_record}
        files.replace(root / JOURNAL, encode(journal), expected=None)
        exchange(stage, app, swap=True)
        recover(root, home)
        return {'restored': True, 'app': str(app), 'kind': previous['kind'], 'capture_setup_pending': True}


def status(root, *, home=None):
    home = (home or Path.home()).absolute()
    app, _ = paths(home)
    existing = record(root, home)
    try:
        running_here = app.exists() and os.path.samefile(source_app(), app)
    except (OSError, ValueError):
        running_here = False
    return {'app': str(app), 'installed': app.exists(), 'managed': existing is not None,
        'running_from_installation': running_here,
        'can_rollback': bool(existing and existing['previous']),
        'cleanup_pending': bool(existing and existing['retired']),
        'recovery_pending': files.read(root / JOURNAL, private=True) is not None or files.read(root / REMOVAL, private=True) is not None}


@maintenance
def remove(root, *, home=None):
    home = (home or Path.home()).absolute()
    app, cli = paths(home)
    no_active(root)
    no_running_app(app)
    with files.locked(root / '.mac-install'):
        if files.read(root / REMOVAL, private=True):
            finish_removal(root, home)
            return {'removed': True, 'history_preserved': True}
        recover(root, home)
        retire(root, home)
        current = record(root, home)
        if not current or app_tree(app)[0] != current['current']['digest']:
            raise ContractError('installed_mac_app_changed')
        # Journal both app moves before disabling the recorded hooks. Recovery
        # preflights every owned file before making those configuration changes.
        items = []
        if current['previous']:
            previous = current['previous']
            items.append(trash_item(Path(previous['path']), previous['digest'], home))
        items.append(trash_item(app, current['current']['digest'], home))
        preflight_removal(items, home)
        removal = {'format': 1, 'app': str(app), 'items': items,
            'cli_expected': current['current']['cli'] if current['cli_managed'] else None}
        files.replace(root / REMOVAL, encode(removal), expected=None)
        finish_removal(root, home)
        return {'removed': True, 'trashed_app': items[-1]['trash'], 'history_preserved': True}
