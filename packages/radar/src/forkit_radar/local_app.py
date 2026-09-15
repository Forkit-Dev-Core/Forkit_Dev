"""Open the existing private history view without a server, signup or source scan."""
from __future__ import annotations

import argparse
import html
import json
import re
import subprocess
import sys
from pathlib import Path

from .capture import setup_files as files
from .capture.automatic import setup, workspace_state
from .capture.automatic import state as setup_state
from .jsonio import load_json
from .sessions.models import TOOL_NAMES
from .sessions.private_view import render
from .sessions.storage import SessionStore
from .sessions.summary import build


def configure(commands):
    p = commands.add_parser('open', help='Open fresh private session history in your browser; no server or account')
    p.add_argument('--store', type=Path)
    p.add_argument('--no-browser', action='store_true', help='Refresh the local file without opening a browser')
    p.add_argument('--json', action='store_true', help=argparse.SUPPRESS)


def capture_panel(root, *, native=False):
    """Show observed status, never infer hook trust from configuration alone.

    Old b4 setup/events have no generation. New or replaced setup gets a new
    generation, so an earlier successful callback cannot hide required review.
    Damaged diagnostics must not prevent opening otherwise valid local history.
    """
    rows = []
    try:
        status = setup(root, inspect=True)
        current = setup_state(root)
        for item in status['agents']:
            agent, configured = item['agent'], item['state']
            if configured == 'not_configured' and not item['detected']:
                continue
            last = None
            try:
                raw = files.read(root / ('capture-status-' + agent + '.json'), private=True)
                last = load_json(raw) if raw else None
                if last and last.get('generation') != current['agents'].get(agent, {}).get('generation'):
                    last = None
            except (OSError, ValueError):
                pass
            result = last.get('result') if last else None
            state, label = 'waiting', 'Waiting for the first session'
            if configured == 'needs_attention':
                state, label = 'attention', 'Capture settings need attention'
            elif configured == 'disabled':
                state, label = 'paused', 'Capture paused'
            elif configured == 'not_configured':
                state, label = 'setup', 'Set up automatic capture'
            elif result == 'capture_needs_attention':
                state, label = 'attention', 'A session could not be captured'
            elif result == 'no_active_capture':
                state, label = 'attention', 'Session start was missed — no receipt saved'
            elif result == 'receipt_saved':
                state, label = 'observed', 'Last receipt saved'
            elif result in {'capture_started', 'duplicate'}:
                state, label = 'observed', 'Session hook received'
            elif result == 'outside_local_git_project':
                state, label = 'waiting', 'Last session was outside a local Git project'
            elif agent == 'codex':
                state, label = 'setup', 'Review Forkit in Codex /hooks, then start a session'
            experimental = ' <span class="badge">Experimental</span>' if agent != 'codex' else ''
            timestamp = last.get('last_event_at') if last else None
            observed_at = f' · {html.escape(timestamp)}' if isinstance(timestamp, str) and re.fullmatch(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z', timestamp) else ''
            activity = ' · local activity enabled' if item.get('local_activity') else ''
            rows.append(f'<div class="capture-line" data-capture-state="{state}"><strong>{html.escape(TOOL_NAMES[agent])}</strong>{experimental}<span>{html.escape(label)}{observed_at}{activity}</span></div>')
    except (OSError, ValueError, TypeError, KeyError):
        rows = ['<div class="capture-line" data-capture-state="attention"><strong>Capture needs attention</strong><span>Your saved receipts are available below.</span></div>']
    if not rows:
        rows = ['<div class="capture-line" data-capture-state="setup"><strong>No coding tool found</strong><span>Install a supported tool, then set up capture.</span></div>']
    instructions = ('<p>Use Capture in the toolbar to set up or pause capture. Use Recover session for a missed end.</p>' if native else
            '<p>Check setup: <code>forkit-radar setup --status</code><br>'
            'Set up or resume: <code>forkit-radar setup</code><br>'
            'Pause: <code>forkit-radar setup --disable</code></p>')
    return ('<section class="capture-panel" aria-label="Automatic local capture">' + ''.join(rows)
            + '<details id="capture-settings"><summary>Capture settings</summary>'
            '<p>Automatic capture works in local Git projects. Codex needs one-time review in <code>/hooks</code>. '
            'Claude Code and Cursor are experimental.</p>'
            + instructions +
            '<p>Receipts appear after the tool ends its session. Codex desktop end events may be delayed. '
            'A missed end remains incomplete; see Help for recovery.</p>'
            '</details></section>')


def refresh(root, *, native=False):
    report = build(SessionStore(root), limit=200)
    raw = render(report, native=native).replace(b'<div class="context">', capture_panel(root, native=native).encode() + b'<div class="context">', 1)
    if not native and workspace_state() != 'eligible_git_project':
        notice = b'<p class="notice">This view was opened from outside an eligible Git project. Saved history is shown below. For new capture, open the actual repository in your coding tool, not its parent folder.</p>'
        raw = raw.replace(b'<div class="context">', notice + b'<div class="context">', 1)
    files.private_directory(root)
    # HTML can be larger than setup JSON. It is private generated output, not
    # a user-supplied report or a source file. Reuse the exclusive document writer
    # for immutable snapshots and keep only the latest generated snapshot pointer.
    from uuid import uuid4

    from .identity.storage import write_new
    # Only publication holds the setup lock; expensive rendering must not delay hooks.
    with files.locked(root):
        path = root / ('history-' + str(uuid4()) + '.html')
        write_new(path, raw)
        pointer = root / 'latest-view.json'
        previous = files.read(pointer, private=True)
        old = load_json(previous).get('file') if previous else None
        try:
            files.replace(pointer, (json.dumps({'file': path.name}) + '\n').encode(), expected=previous)
        except (OSError, ValueError):
            path.unlink(missing_ok=True)
            raise
        # Remove only our recorded previous generated view; never user exports.
        if isinstance(old, str) and re.fullmatch(r'history-[0-9a-f-]{36}\.html', old):
            old_path = root / old
            if not old_path.is_symlink():
                old_path.unlink(missing_ok=True)
        return path


def command(args):
    try:
        root = (args.store or Path.home() / '.forkit-radar').expanduser().absolute()
        path = refresh(root)
        if not args.no_browser:
            if sys.platform == 'darwin':
                argv = ['/usr/bin/open', str(path)]
            elif sys.platform == 'linux':
                argv = ['xdg-open', str(path)]
            else:
                raise ValueError('unsupported_browser_launcher')
            subprocess.run(argv, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10, check=True)
        if args.json:
            print(json.dumps({'file': str(path), 'private': True, 'account_required': False}))
        else:
            print('Private history refreshed locally. No signup or upload. ' + str(path))
        return 0
    except (OSError, ValueError, subprocess.SubprocessError):
        print('Local history needs attention. Run setup --status and storage status. Your receipts are preserved.', file=sys.stderr)
        return 1
