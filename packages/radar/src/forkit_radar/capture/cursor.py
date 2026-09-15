"""Cursor local single-workspace lifecycle; fire-and-forget baseline is partial."""
from ..jsonio import ContractError
from .common import envelope
from ..jsonio import load_json


def parse(raw, project):
    activity = load_json(raw).get('hook_event_name') in {'postToolUse', 'postToolUseFailure'}
    data, identity = envelope(raw, project, cursor=True, activity=activity)
    event = data.get('hook_event_name')
    if event in {'postToolUse', 'postToolUseFailure'}:
        return 'activity', identity
    if event == 'sessionStart':
        return 'start', identity
    if event == 'sessionEnd':
        return 'end', identity
    raise ContractError('unsupported_hook_event')
