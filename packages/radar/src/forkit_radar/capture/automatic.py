"""Install-once user hooks. Agent events select local Git roots, never a home scan.

This is local setup consent, not agent identity authentication or usage consent.
No transcript is opened. No repository hook or other discovered command is run.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import shlex
import shutil
import sys
from pathlib import Path
from uuid import uuid4

from ..discovery.collectors import applications
from ..discovery.safeio import directory
from ..identity.passports import now
from ..jsonio import ContractError, load_json
from ..lifecycle import guard
from ..sessions.inventory import select_project
from . import setup_files as files
from .cli import ADAPTERS, receive

STATE = 'automatic-capture.json'


def encode(value):
    return (json.dumps(value, indent=2, ensure_ascii=True) + '\n').encode()


def detected(home):
    found = {agent for agent, executable in [('codex', 'codex'), ('claude-code', 'claude'), ('cursor', 'cursor')]
             if shutil.which(executable)}
    for result in applications(home):
        found.update(c.product for c in result.candidates if c.product in ADAPTERS)
    return found


def config_paths(home):
    # Respect the coding tools' explicit user configuration roots. Never change
    # either variable or copy another profile's trust, chats or credentials.
    return {
        'codex': Path(os.environ.get('CODEX_HOME') or home / '.codex').expanduser().absolute() / 'hooks.json',
        'claude-code': Path(os.environ.get('CLAUDE_CONFIG_DIR') or home / '.claude').expanduser().absolute() / 'settings.json',
        'cursor': home / '.cursor/hooks.json',
    }


def state(root):
    raw = files.read(root / STATE, private=True)
    result = load_json(raw) if raw else {'format': 1, 'agents': {}}
    if set(result) != {'format', 'agents'} or result['format'] != 1 or not isinstance(result['agents'], dict) or not set(result['agents']) <= set(ADAPTERS):
        raise ContractError('invalid_automatic_setup_state')
    for item in result['agents'].values():
        if not isinstance(item, dict) or not isinstance(item.get('enabled'), bool) or not isinstance(item.get('groups'), dict):
            raise ContractError('invalid_automatic_setup_entry')
    return result


def save(root, value):
    path = root / STATE
    files.replace(path, encode(value), expected=files.read(path, private=True))


def groups(agent, root, executable=None):
    python = Path(executable or sys.executable)
    # Normalize directory aliases such as macOS /tmp -> /private/tmp, without
    # resolving the final Python symlink out of a virtual environment.
    python = python.parent.resolve() / python.name
    command = shlex.join([str(python), '-I', '-B', '-m', 'forkit_radar', 'hooks', 'auto', '--agent', agent, '--store', str(root)])
    if agent == 'cursor':
        return {event: [{'command': command}] for event in ('sessionStart', 'sessionEnd')}
    return {
        'SessionStart': [{'matcher': '^(startup|resume|clear)$', 'hooks': [{'type': 'command', 'command': command, 'timeout': 10}]}],
        'SessionEnd': [{'hooks': [{'type': 'command', 'command': command, 'timeout': 3 if agent == 'codex' else 10}]}],
    }


def parsed_config(raw, agent):
    value = load_json(raw) if raw is not None else {}
    hooks = value.get('hooks', {})
    if not isinstance(hooks, dict) or any(not isinstance(v, list) for v in hooks.values()):
        raise ContractError('existing_hook_shape_unsupported')
    if value.get('disableAllHooks') is True:
        raise ContractError('hooks_disabled_by_user')
    if agent == 'cursor' and ('version' in value and (type(value['version']) is not int or value['version'] != 1)):
        raise ContractError('unsupported_cursor_hook_version')
    return value


def contains(value, owned):
    hooks = value.get('hooks', {})
    return all(hooks.get(event, []).count(group) == 1 for event, entries in owned.items() for group in entries)


def without(value, owned):
    value = copy.deepcopy(value)
    hooks = value.get('hooks', {})
    for event, entries in owned.items():
        for group in entries:
            if group in hooks.get(event, []):
                hooks[event].remove(group)
        if event in hooks and not hooks[event]:
            del hooks[event]
    return value


def original_bytes(root, item):
    backup = item['backup']
    if backup is not None and (Path(backup).name != backup or not backup.startswith('setup-backup-')):
        raise ContractError('invalid_setup_backup')
    before = files.read(root / backup, private=True) if backup else None
    if files.digest(before) != item['before_sha256']:
        raise ContractError('setup_backup_changed')
    return before


def install_agent(agent, root, path, executable=None):
    current = state(root)
    previous = current['agents'].get(agent)
    if previous and previous.get('path') != str(path):
        raise ContractError('disable_previous_profile_before_switching')
    raw = files.read(path)
    value = parsed_config(raw, agent)
    before = raw
    owned = groups(agent, root, executable)
    if previous and previous['enabled'] and previous['groups'] == owned and contains(value, owned):
        return 'configured_review_in_tool' if agent == 'codex' else 'configured_experimental'
    if previous:
        # If an owned definition was edited, leave it for review rather than
        # deleting a lookalike or adding a second automatic collector.
        if previous['enabled'] and not contains(value, previous['groups']):
            raise ContractError('forkit_hooks_changed_review_before_repair')
        value = without(value, previous['groups'])
        if files.digest(raw) == previous['after_sha256']:
            before = original_bytes(root, previous)
        elif contains(parsed_config(raw, agent), previous['groups']):
            before = encode(value)
    hooks = value.setdefault('hooks', {})
    for event, entries in owned.items():
        if any(entry in hooks.get(event, []) for entry in entries):
            raise ContractError('unowned_forkit_definition_review_required')
        hooks.setdefault(event, []).extend(entries)
    if agent == 'cursor':
        value['version'] = 1
    after = encode(value)
    if len(after) > 65_536:
        raise ContractError('merged_hook_config_too_large')
    if not path.parent.exists():
        files.private_directory(path.parent)
    backup = None
    if before is not None:
        backup = 'setup-backup-' + str(uuid4()) + '.json'
        files.replace(root / backup, before, expected=None)
    # Persist the recovery inventory before touching the coding tool's config.
    # The callback remains disabled until publication succeeds.
    entry = {'enabled': False, 'phase': 'pending', 'generation': str(uuid4()), 'path': str(path), 'groups': owned, 'backup': backup,
             'before_sha256': files.digest(before), 'after_sha256': files.digest(after)}
    current['agents'][agent] = entry
    save(root, current)
    files.replace(path, after, expected=raw)
    entry['enabled'] = True
    entry['phase'] = 'enabled'
    save(root, current)
    return 'configured_review_in_tool' if agent == 'codex' else 'configured_experimental'


def disable_agent(agent, root):
    current = state(root)
    item = current['agents'].get(agent)
    if item is None:
        return 'not_configured'
    if item.get('phase') == 'disabled':
        return 'disabled'
    # Disable first, even if later config cleanup needs manual attention.
    item['enabled'] = False
    item['phase'] = 'disabling'
    save(root, current)
    path = Path(item['path'])
    raw = files.read(path)
    if raw is None:
        item['phase'] = 'disabled'
        save(root, current)
        return 'disabled'
    if files.digest(raw) == item['after_sha256']:
        before = original_bytes(root, item)
        files.replace(path, before, expected=raw)
    else:
        value = parsed_config(raw, agent)
        if not contains(value, item['groups']):
            raise ContractError('disabled_config_cleanup_needs_review')
        files.replace(path, encode(without(value, item['groups'])), expected=raw)
    item['phase'] = 'disabled'
    save(root, current)
    return 'disabled'


def setup(root, *, agents=None, disable=False, inspect=False, home=None, executable=None):
    home = home or Path.home()
    root = root.expanduser().absolute()
    available = detected(home)
    current = state(root)
    targets = set(agents) if agents else (set(current['agents']) if disable else available | set(current['agents']))
    paths = config_paths(home)
    results = []
    if inspect:
        for agent in ADAPTERS:
            item = current['agents'].get(agent)
            configured = False
            if item and item['enabled']:
                try:
                    configured = contains(parsed_config(files.read(Path(item['path'])), agent), item['groups'])
                except (OSError, ValueError):
                    pass
            results.append({'agent': agent, 'detected': agent in available, 'state':
                            'needs_attention' if item and item.get('phase') in {'pending', 'disabling'} else
                            ('configured_review_in_tool' if agent == 'codex' else 'configured_experimental') if configured else
                            ('needs_attention' if item and item['enabled'] else 'disabled' if item else 'not_configured')})
    elif targets:
        with guard(root, exclusive=True), files.locked(root):
            for agent in sorted(targets):
                try:
                    result = disable_agent(agent, root) if disable else install_agent(agent, root, paths[agent], executable)
                except (OSError, ValueError):
                    result = 'needs_attention'
                results.append({'agent': agent, 'detected': agent in available, 'state': result})
    return {'format': 1, 'kind': 'forkit_automatic_setup', 'agents': results,
            'account_required': False, 'reporting_enabled_by_setup': False,
            'scope': 'local_git_projects_reported_by_enabled_tools',
            'hook_trust': 'review_required_in_codex_not_bypassed',
            'ready': (any(r['state'].startswith('configured_') for r in results) if not disable else bool(results))
                     and all(r['state'] != 'needs_attention' for r in results)}


def project_for_event(data, agent, home):
    roots = data.get('workspace_roots') if agent == 'cursor' else [data.get('cwd')]
    if not isinstance(roots, list) or len(roots) != 1 or not isinstance(roots[0], str):
        raise ContractError('one_local_workspace_required')
    cwd = Path(roots[0])
    if not cwd.is_absolute():
        raise ContractError('absolute_hook_workspace_required')
    # Let the adapter reject event types, background sessions and bad IDs before
    # any repository is touched. Raw transcripts/prompts are never opened.
    action, _ = ADAPTERS[agent].parse(encode(data), cwd)
    if action == 'ignore':
        return None
    with directory(cwd):
        pass
    forbidden = {Path('/'), home, home / 'Desktop', home / 'Documents', home / 'Downloads',
                 home / 'Library', Path('/Users'), Path('/Volumes'), Path('/tmp'), Path('/private/tmp')}
    for candidate in (cwd, *cwd.parents):
        if candidate in forbidden:
            break
        if (candidate / '.git').exists():
            return select_project(candidate)[0]
    return None


def automatic_receive(agent, root, raw):
    item = state(root)['agents'].get(agent)
    if not item or not item['enabled']:
        return
    try:
        with guard(root):
            return _automatic_receive(agent, root, raw)
    except (OSError, ValueError):
        note_event(root, agent, 'capture_needs_attention', item.get('generation'))
        raise


def _automatic_receive(agent, root, raw):
    # Re-read under the lifecycle lock: a pause may have won before acquisition.
    current = state(root)
    item = current['agents'].get(agent)
    if not item or not item['enabled']:
        return
    data = load_json(raw)
    project = project_for_event(data, agent, Path.home())
    if project is None:
        result = 'outside_local_git_project'
        note_event(root, agent, result, item.get('generation'))
        return  # Normal non-project chats are out of scope, not failures.
    # The adapter still checks the exact root and scoped external session token.
    if agent == 'cursor':
        data['workspace_roots'] = [str(project)]
    else:
        data['cwd'] = str(project)
    args = argparse.Namespace(agent=agent, project=project, store=root,
                              agent_manifest=None, registry=None, passport_id=None,
                              automatic_selection=True)
    result = receive(args, encode(data))
    note_event(root, agent, result, item.get('generation'))


def note_event(root, agent, result, generation):
    # Fixed local status only; never event input, paths, IDs or exception text.
    path = root / ('capture-status-' + agent + '.json')
    try:
        files.replace(path, encode({'agent': agent, 'last_event_at': now(), 'result': result, 'generation': generation}), expected=files.read(path, private=True))
    except (OSError, ValueError):
        pass  # Diagnostic failure cannot invalidate a committed receipt.


def configure(commands):
    p = commands.add_parser('setup', help='Enable install-once automatic local capture for detected coding tools')
    action = p.add_mutually_exclusive_group()
    action.add_argument('--status', action='store_true', help='Inspect setup without changing configuration')
    action.add_argument('--disable', action='store_true', help='Disable callbacks and remove only Forkit-owned hooks; keep history')
    p.add_argument('--agent', choices=tuple(ADAPTERS), action='append', help='Select a tool explicitly; otherwise detect installed tools')
    p.add_argument('--store', type=Path)
    p.add_argument('--json', action='store_true')


def command(args):
    try:
        result = setup(args.store or Path.home() / '.forkit-radar', agents=args.agent,
                       disable=args.disable, inspect=args.status)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print('Forkit automatic local capture' + (' — status' if args.status else ''))
            for item in result['agents']:
                print(item['agent'] + ': ' + item['state'].replace('_', ' '))
            if not result['agents']:
                print('No supported coding tool detected. Install one, then run forkit-radar setup again.')
            if not args.disable:
                print('Codex: restart and review the Forkit definitions in /hooks once. Capture begins with your next session.')
                print('Claude Code / Cursor: experimental. Cursor starts are partial. Managed policies can disable hooks.')
                print('Open Forkit to see receipts after sessions end. Codex desktop end events may be delayed.')
            else:
                print('Any still-active capture keeps its baseline. Use session active and session recover ID after stopping work; its end time remains unknown.')
            print('No Forkit account or repository connection. Local history stays private. Reporting was not enabled.')
        return 0 if not any(r['state'] == 'needs_attention' for r in result['agents']) else 1
    except (OSError, ValueError, TypeError, KeyError):
        print('Automatic setup needs attention. Existing history is preserved; check configuration permissions or run setup --status.', file=sys.stderr)
        return 1
