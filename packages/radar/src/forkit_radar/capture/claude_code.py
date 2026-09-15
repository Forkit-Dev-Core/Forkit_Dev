"""Claude Code official lifecycle settings; experimental until live CLI validation."""
from .common import envelope
from ..jsonio import ContractError


def parse(raw, project):
    data, identity = envelope(raw, project)
    if data.get('hook_event_name') == 'SessionStart':
        if data.get('source') == 'compact':
            return 'ignore', identity
        if data.get('source') not in {'startup', 'resume', 'clear'}:
            raise ContractError('unsupported_hook_start_source')
        return 'start', identity
    if data.get('hook_event_name') == 'SessionEnd':
        return 'end', identity
    raise ContractError('unsupported_hook_event')
