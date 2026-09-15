"""Cursor local single-workspace lifecycle; fire-and-forget baseline is partial."""
from .common import envelope
from ..jsonio import ContractError


def parse(raw, project):
    data, identity = envelope(raw, project, cursor=True)
    event = data.get('hook_event_name')
    if event == 'sessionStart':
        return 'start', identity
    if event == 'sessionEnd':
        return 'end', identity
    raise ContractError('unsupported_hook_event')
