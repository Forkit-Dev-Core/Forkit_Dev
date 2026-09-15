"""Create reviewable official project hooks; callbacks are local and quiet."""
from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path

from ..identity.storage import write_new
from ..jsonio import MAX_DOCUMENT_BYTES, ContractError, load_json
from ..sessions.cli import selected
from ..sessions.inventory import select_project
from ..sessions.storage import SessionStore
from . import claude_code, codex, cursor

ADAPTERS = {'codex': codex, 'claude-code': claude_code, 'cursor': cursor}
CONFIG = {'codex': '.codex/hooks.json', 'claude-code': '.claude/settings.local.json', 'cursor': '.cursor/hooks.json'}


def configure(commands):
    parser = commands.add_parser('hooks', help='Set up official automatic session hooks in one Git project; no account')
    actions = parser.add_subparsers(dest='hook_action', required=True)
    automatic = actions.add_parser('auto', help=argparse.SUPPRESS)
    automatic.add_argument('--agent', choices=tuple(ADAPTERS), required=True)
    automatic.add_argument('--store', type=Path, required=True)
    for action in ('setup', 'print', 'receive'):
        command = actions.add_parser(action, help='Print configuration for review/merging' if action == 'print' else None)
        command.add_argument('--agent', choices=tuple(ADAPTERS), required=True)
        command.add_argument('--project', type=Path)
        command.add_argument('--store', type=Path)
        command.add_argument('--agent-manifest', type=Path)
        command.add_argument('--registry', type=Path)
        command.add_argument('--passport-id')


def configuration(args, project):
    argv = [sys.executable, '-I', '-m', 'forkit_radar', 'hooks', 'receive', '--agent', args.agent,
            '--project', str(project), '--store', str(args.store.absolute())]
    for name in ('agent_manifest', 'registry', 'passport_id'):
        value = getattr(args, name)
        if value is not None:
            argv.extend(['--' + name.replace('_', '-'), str(value.absolute() if isinstance(value, Path) else value)])
    command = shlex.join(argv)
    if args.agent == 'cursor':
        return {'version': 1, 'hooks': {event: [{'command': command}] for event in ('sessionStart', 'sessionEnd')}}
    return {'hooks': {
        'SessionStart': [{'matcher': '^(startup|resume|clear)$', 'hooks': [{'type': 'command', 'command': command, 'timeout': 10}]}],
        'SessionEnd': [{'hooks': [{'type': 'command', 'command': command, 'timeout': 3 if args.agent == 'codex' else 10}]}],
    }}


def receive(args, raw):
    project, _ = select_project(args.project)
    action, identity = ADAPTERS[args.agent].parse(raw, project)
    if action == 'ignore':
        return 'ignored'
    store = SessionStore(args.store)
    if action == 'activity':
        if not getattr(args, 'activity', False):
            return 'activity_disabled'
        current = store.active_in(project)
        if not current:
            return 'activity_no_active_capture'
        from .activity import record
        return record(store, current, args.agent, identity, load_json(raw))
    if action == 'start':
        if store.root == project or project in store.root.parents:
            raise ContractError('session_store_must_be_outside_project')
        store.initialize()
    current = store.active_in(project)
    if current:
        # Match an exact agent + private external-session token. Never stop a
        # wrapper/manual receipt or another concurrent agent's interval.
        if not store.matches_hook(current, args.agent, identity):
            if store.active_in(project) is None:
                return 'no_active_capture'  # Another end committed since the read.
            raise ContractError('another_capture_active_use_wrapper_or_separate_worktree')
        if action == 'start':
            return 'duplicate'  # compact does not reset the baseline
        try:
            receipt = store.finish(current.started.session_id, outcome='hook_end')
        except ContractError as error:
            if str(error) != 'session_already_finished':
                raise
            return 'duplicate'  # Exact token matched before another end won.
        from ..reporting.usage_capture import safely_record
        safely_record('receipt', store, receipt)
        return 'receipt_saved'
    elif action == 'start':
        if getattr(args, 'automatic_selection', False):
            from ..sessions.associations import selection_for
            choice = selection_for(args.store, project)
        else:
            choice = selected(args)
        try:
            store.start(project, tool=args.agent, mode='official_hook', selection=choice,
                        hook_identity=identity, observe_activity=getattr(args, 'activity', False))
        except ContractError as error:
            if str(error) != 'active_session_exists_stop_or_recover_it':
                raise
            winner = store.active_in(project)
            if winner is None or not store.matches_hook(winner, args.agent, identity):
                raise
            return 'duplicate'  # Concurrent delivery of the same start only.
        return 'capture_started'
    # A duplicate/end-without-start never creates a retroactive receipt.
    return 'no_active_capture'


def command(args):
    try:
        if args.hook_action == 'auto':
            from .automatic import automatic_receive
            automatic_receive(args.agent, args.store, sys.stdin.buffer.read(MAX_DOCUMENT_BYTES + 1))
            return 0
        args.project = args.project or Path.cwd()
        args.store = args.store or Path.home() / '.forkit-radar'
        if args.hook_action == 'receive':
            receive(args, sys.stdin.buffer.read(MAX_DOCUMENT_BYTES + 1))
            return 0  # no model context, paths, or receipt content on hook stdout
        project, _ = select_project(args.project)
        raw = (json.dumps(configuration(args, project), indent=2) + '\n').encode()
        if args.hook_action == 'print':
            print(raw.decode(), end='')
            return 0
        path = project / CONFIG[args.agent]
        if path.exists() or path.is_symlink():
            raise ContractError('hook_config_exists_use_hooks_print_and_merge_after_review')
        # Refuse symlinked parents via the existing safe document writer.
        path.parent.mkdir(mode=0o700, exist_ok=True)
        write_new(path, raw)
        print('Project hooks created. Restart your coding tool. Local capture needs no Forkit account.')
        if args.agent == 'codex':
            print('In Codex, trust this project and review/enable the exact hooks with /hooks. No trust bypass is installed.')
            print('SessionEnd can be delayed in the desktop app; use the wrapper for a precise command boundary.')
        else:
            print('Experimental adapter: verify it with session active and receipt before relying on capture.')
        if args.agent == 'cursor':
            print('Cursor capture is partial: sessionStart does not wait for the baseline. Local single-workspace sessions only.')
        print('After the tool exits: forkit-radar receipt. Missing end event: session active, then session recover <id>.')
        return 0
    except (OSError, ValueError, TypeError):
        # Never reflect rejected payload, prompt, paths or credentials.
        print('Hook capture/setup unavailable. Check project, existing configuration and active sessions; use hooks print to review configuration. Local history is preserved.', file=sys.stderr)
        return 1  # Non-blocking failure on official command-hook protocols.
