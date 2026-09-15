"""Codex official SessionStart/SessionEnd (main thread, not per turn)."""
from ..jsonio import ContractError
from .common import envelope


def parse(raw, project):
    data, identity = envelope(raw, project)
    event = data.get('hook_event_name')
    if event == 'SessionStart':
        if data.get('source') == 'compact':
            return 'ignore', identity
        if data.get('source') not in {'startup', 'resume', 'clear'}:
            raise ContractError('unsupported_hook_start_source')
        return 'start', identity
    if event == 'SessionEnd':
        return 'end', identity
    raise ContractError('unsupported_hook_event')
