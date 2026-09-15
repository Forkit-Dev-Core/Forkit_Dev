"""Opt-in, bounded tool-reported metadata. Never retain raw hook input/output.

This is a private annotation beside immutable change receipts, not network proof.
Only explicitly supported URL argument shapes reveal a destination. A shell
command, search query/result, or MCP name never proves a network request.
"""
from __future__ import annotations

import hashlib
import hmac
import ipaddress
import re
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field

from ..contracts import Contract, Digest, Text
from ..identity.passports import now
from ..jsonio import ContractError, load_json
from ..lifecycle import session_operation
from ..sessions.models import Array

LIMIT = 128
KINDS = {'web_fetch': 'Web fetch', 'browser_navigation': 'Browser navigation',
         'http_tool': 'HTTP tool', 'mcp_tool': 'MCP tool', 'web_search': 'Web search'}
STATES = {'tool_reported_success': 'Tool reported success',
          'tool_reported_failure': 'Tool reported failure', 'tool_returned': 'Tool returned'}
EVENTS = {'codex': ('PostToolUse',),
          'claude-code': ('PostToolUse', 'PostToolUseFailure'),
          'cursor': ('postToolUse', 'postToolUseFailure')}


class Event(Contract):
    token: Digest
    time: Annotated[Text, Field(pattern=r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$')]
    kind: Literal['web_fetch', 'browser_navigation', 'http_tool', 'mcp_tool', 'web_search']
    destination: Annotated[str, Field(max_length=253, pattern=r'^[a-z0-9.:-]+$')] | None = None
    outcome: Literal['tool_reported_success', 'tool_reported_failure', 'tool_returned']


class Log(Contract):
    schema_version: Literal['1.0'] = '1.0'
    events: Annotated[Array[Event], Field(max_length=LIMIT)] = ()
    truncated: bool = False


def hostname(value):
    if not isinstance(value, str) or len(value) > 8192 or any(c.isspace() for c in value):
        return None
    try:
        parsed = urlsplit(value)
        if parsed.scheme not in {'http', 'https'} or not parsed.hostname:
            return None
        # Never persist userinfo, path, query, fragment or port. Private IPs and
        # local/internal names are intentionally coarsened rather than exposed.
        host = parsed.hostname.rstrip('.').encode('idna').decode('ascii').lower()
        if len(host) > 253 or not re.fullmatch(r'[a-z0-9.:-]+', host):
            return None
        try:
            address = ipaddress.ip_address(host)
            return 'local-network' if not address.is_global else str(address)
        except ValueError:
            if host == 'localhost' or '.' not in host or host.endswith(('.localhost', '.local', '.internal', '.test', '.invalid')):
                return 'localhost' if host == 'localhost' else 'local-network'
        return host
    except (ValueError, UnicodeError):
        return None


def observation(data, agent):
    """Return fixed categories and one safe host; no arbitrary tool labels."""
    name = data.get('tool_name')
    call_id = data.get('tool_use_id')
    if not isinstance(name, str) or not isinstance(call_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,200}', call_id):
        return None  # No reliable dedupe key: don't inflate activity counts.
    inputs = data.get('tool_input')
    inputs = inputs if isinstance(inputs, dict) else {}
    kind, host = None, None
    if agent == 'claude-code' and name == 'WebFetch':
        kind, host = 'web_fetch', hostname(inputs.get('url'))
    elif agent == 'claude-code' and name == 'WebSearch':
        kind = 'web_search'  # Queries, filters and results are not visits.
    elif (name.startswith('mcp__') and len(name.split('__')) >= 3) or (agent == 'cursor' and name.startswith('MCP:')):
        operation = name.removeprefix('MCP:').rsplit('__', 1)[-1]
        kind = {'browser_navigate': 'browser_navigation', 'fetch': 'web_fetch',
                'http_request': 'http_tool'}.get(operation, 'mcp_tool')
        if kind != 'mcp_tool':
            host = hostname(inputs.get('url'))
    if kind is None:
        return None  # Shell commands/code, hosted tools and unknown shapes excluded.
    event = data['hook_event_name']
    outcome = ('tool_reported_failure' if event in {'PostToolUseFailure', 'postToolUseFailure'}
               else 'tool_returned' if agent == 'codex' else 'tool_reported_success')
    return call_id, {'kind': kind, 'destination': host, 'outcome': outcome}


def initial_bytes():
    return Log().model_dump_json().encode()


def read_log(db, session_id):
    row = db.execute('SELECT value FROM settings WHERE name=?', ('activity:' + session_id,)).fetchone()
    if row is None:
        return None
    if not isinstance(row[0], bytes) or len(row[0]) > 65536:
        raise ContractError('invalid_activity_annotation')
    return Log.model_validate(load_json(row[0]))


def view(db, session_id):
    try:
        log = read_log(db, session_id)
    except (ValueError, TypeError):
        return {'state': 'unavailable', 'events': [], 'truncated': False}
    if log is None:
        return {'state': 'not_enabled', 'events': [], 'truncated': False}
    # Local event tokens are only for deduplication, never rendered/exported.
    return {'state': 'partial', 'events': [e.model_dump(exclude={'token'}) for e in log.events],
            'truncated': log.truncated}


@session_operation
def record(store, entry, agent, identity, data):
    item = observation(data, agent)
    if item is None:
        return 'activity_unsupported'
    call_id, fields = item
    with store._connect(write=True) as db:
        # Recheck the binding and active state under the same transaction as the
        # annotation write. Late callbacks cannot attach to a different session.
        row = db.execute('SELECT session_id, project_id, state, started FROM sessions WHERE session_id=?',
                         (entry.started.session_id,)).fetchone()
        active = store._entry(row)
        if active.state != 'active' or active.started.capture_mode != 'official_hook' or active.started.tool != agent:
            return 'activity_no_active_capture'
        token = db.execute('SELECT value FROM settings WHERE name=?', ('hook:' + entry.started.session_id,)).fetchone()
        if not token or not hmac.compare_digest(token[0], store._hook_token(store._key(db), agent, identity)):
            return 'activity_session_mismatch'
        log = read_log(db, entry.started.session_id)
        if log is None:
            return 'activity_not_enabled_at_start'
        event_token = hmac.new(store._key(db), ('forkit-activity-v1\n' + entry.started.session_id + '\n' + agent + '\n' + call_id).encode(), hashlib.sha256).hexdigest()
        if any(e.token == event_token for e in log.events):
            return 'activity_duplicate'
        if len(log.events) >= LIMIT:
            log = log.model_copy(update={'truncated': True})
        else:
            event = Event(token=event_token, time=now(), **fields)
            log = log.model_copy(update={'events': (*log.events, event)})
        db.execute('UPDATE settings SET value=? WHERE name=?',
                   (log.model_dump_json().encode(), 'activity:' + entry.started.session_id))
    return 'activity_recorded'
