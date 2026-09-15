"""Allowlisted lifecycle envelope; everything else is discarded in memory."""
import re
from pathlib import Path

from ..jsonio import ContractError, load_json


def envelope(raw, project, *, cursor=False, activity=False):
    data = load_json(raw)
    identity = data.get('session_id', data.get('conversation_id') if cursor else None)
    if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}', identity):
        raise ContractError('invalid_hook_session')
    roots = data.get('workspace_roots') if cursor else [data.get('cwd')]
    # Multiple workspaces and background/cloud sessions need their own boundaries.
    if cursor and data.get('is_background_agent') is not False and (not activity or data.get('is_background_agent') is not None):
        raise ContractError('background_hook_unsupported')
    if activity and (data.get('subagent_id') or data.get('is_parallel_worker')):
        raise ContractError('background_hook_unsupported')
    if not isinstance(roots, list) or len(roots) != 1 or not isinstance(roots[0], str):
        raise ContractError('hook_project_required')
    if Path(roots[0]).absolute() != project.absolute():
        raise ContractError('hook_project_mismatch')
    return data, identity
