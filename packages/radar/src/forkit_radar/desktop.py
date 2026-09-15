"""Bounded local subprocess interface for the Mac app. No listener or network.

Requests come from native controls as JSON on stdin, never from project scripts.
Each operation reuses the CLI's existing capture, identity and storage primitives.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

from .capture import setup_files as files
from .capture.automatic import setup, state
from .discovery.safeio import directory
from .identity.passports import core_json, create_bytes, lookup
from .jsonio import ContractError, load_json
from .local_app import refresh
from .sessions.associations import associations, checked_project, choose, projects
from .sessions.storage import SessionStore


def request():
    raw = sys.stdin.buffer.read(16_385)
    if len(raw) > 16_384:
        raise ContractError('desktop_request_too_large')
    return load_json(raw) if raw else {}


def fields(data, expected):
    if set(data) != set(expected):
        raise ContractError('invalid_desktop_request')


def text(value, limit=160):
    if not isinstance(value, str) or not value.strip() or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ContractError('required_metadata_missing')
    return value.strip()


def local_registry(root):
    """Guard the app-owned Core registry before calling its existing writer."""
    registry = root / 'registry'
    files.private_directory(registry)
    paths = list(registry.rglob('*'))
    if len(paths) > 10_000:
        raise ContractError('local_registry_limit')
    for p in [registry, *paths]:
        info = p.lstat()
        if info.st_uid != os.geteuid() or info.st_mode & 0o077 or not (stat.S_ISDIR(info.st_mode) or stat.S_ISREG(info.st_mode)):
            raise ContractError('private_local_registry_required')
        if stat.S_ISREG(info.st_mode) and (info.st_nlink != 1 or info.st_size > 16_777_216):
            raise ContractError('unsafe_local_registry_file')
    return registry


def create_passport(root, data):
    fields(data, {'project_id', 'name', 'version', 'creator', 'model_name', 'model_version'})
    values = {key: text(value) for key, value in data.items()}
    # Validate the physical project before any identity write.
    checked_project(root, values['project_id'])
    from forkit.domain.identity import validate_version
    try:
        validate_version(values['version'])
        validate_version(values['model_version'])
    except ValueError:
        raise ContractError('passport_version_format') from None
    model = create_bytes(json.dumps({'passport_type': 'model', 'name': values['model_name'],
        'version': values['model_version'], 'creator': {'name': values['creator']},
        'task_type': 'code-generation', 'architecture': 'other'}).encode())
    model_id = core_json(model)['id']
    agent = create_bytes(json.dumps({'passport_type': 'agent', 'name': values['name'],
        'version': values['version'], 'creator': {'name': values['creator']}, 'model_id': model_id,
        'task_type': 'code-assistant', 'architecture': 'Custom'}).encode(), model_passport=model)
    agent_id = core_json(agent)['id']
    from forkit.registry.local import LocalRegistry
    from forkit.schemas import AgentPassport, ModelPassport
    with files.locked(root):
        registry = local_registry(root)
        previous_mask = os.umask(0o077)
        try:
            core = LocalRegistry(registry)
            if not (registry / 'models' / (model_id + '.json')).exists():
                core.register_model(ModelPassport.from_dict(core_json(model)), record_change=False)
            if not (registry / 'agents' / (agent_id + '.json')).exists():
                core.register_agent(AgentPassport.from_dict(core_json(agent)), record_change=False)
        finally:
            os.umask(previous_mask)
    choose(root, values['project_id'], registry=registry, passport_id=agent_id)
    return {'passport_id': agent_id, 'model_id': model_id, 'name': values['name'], 'version': values['version']}


def passport_options(root, registry=None):
    """List checked existing identities without constructing or repairing a registry."""
    roots = [Path(text(registry, 4096)).expanduser().absolute()] if registry is not None else [root / 'registry', Path.home() / '.forkit/registry']
    result, skipped, unavailable = [], 0, 0
    for candidate in dict.fromkeys(roots):
        try:
            with directory(candidate / 'agents') as fd:
                names = []
                with os.scandir(fd) as entries:
                    for entry in entries:
                        names.append(entry.name)
                        if len(names) > 512:
                            raise ContractError('local_passport_list_limit')
        except FileNotFoundError:
            if registry is not None:
                raise ContractError('local_registry_unavailable') from None
            continue
        except OSError:
            if registry is not None:
                raise ContractError('local_registry_unavailable') from None
            unavailable += 1
            continue
        for name in sorted(names):
            if not re.fullmatch(r'[0-9a-f]{64}\.json', name):
                continue
            check = lookup(candidate, name[:-5], kind='agent')
            if check.status != 'consistent' or lookup(candidate, check.model_id, kind='model').status != 'consistent':
                skipped += 1
                continue
            result.append({'registry': str(candidate), 'id': check.passport_id,
                'name': check.identity.name, 'version': check.identity.version})
    return {'passports': sorted(result, key=lambda p: (p['name'], p['version'], p['id'])),
        'skipped': skipped, 'unavailable_registries': unavailable}


def perform(action, root, data):
    if action in {'usage-status', 'usage-enable', 'usage-disable', 'engagement'}:
        from .reporting.usage_storage import UsageStore, root as usage_root
        from .reporting.usage_contracts import ENGAGEMENT_POLICY
        usage = UsageStore(usage_root())
        if action == 'usage-status':
            fields(data, set())
            result = usage.status()
            result['has_receipt'] = bool(SessionStore(root).history(limit=1))
            return result
        if action == 'usage-enable':
            fields(data, {'endpoint', 'consent'})
            if data['consent'] != ENGAGEMENT_POLICY or not SessionStore(root).history(limit=1):
                raise ContractError('first_receipt_and_usage_v3_consent_required')
            usage.enable(text(data['endpoint'], 300), consent=ENGAGEMENT_POLICY)
            return {'saved': True, 'sent': False}
        if action == 'usage-disable':
            fields(data, set())
            usage.disable()
            return {'disabled': True}
        fields(data, {'action'})
        if data['action'] not in {'view', 'history', 'card'}:
            raise ContractError('invalid_engagement_action')
        if SessionStore(root).history(limit=1):
            from .reporting.usage_capture import engagement
            engagement(data['action'])
        return {'handled': True}
    if action.startswith('app-'):
        fields(data, set())
        from . import mac_install
        functions = {'app-status': mac_install.status, 'app-install': mac_install.install,
            'app-repair': mac_install.repair, 'app-rollback': mac_install.rollback, 'app-remove': mac_install.remove}
        if action not in functions:
            raise ContractError('unknown_desktop_action')
        return functions[action](root)
    if action == 'render':
        fields(data, set())
        path = refresh(root, native=True)
        return {'file': str(path), 'store': str(root)}
    if action == 'status':
        fields(data, set())
        return {'capture': setup(root, inspect=True), 'active': [e.model_dump(mode='json') for e in SessionStore(root).active()]}
    if action in {'setup', 'pause'}:
        fields(data, set())
        return setup(root, disable=action == 'pause')
    if action == 'onboard':
        fields(data, set())
        current = state(root)
        if not current['agents']:
            return setup(root)
        enabled = [key for key, item in current['agents'].items() if item['enabled']]
        # Update stable app paths after an install, but preserve a user's pause.
        return setup(root, agents=enabled) if enabled else setup(root, inspect=True)
    if action == 'projects':
        fields(data, set())
        return {'projects': projects(SessionStore(root)), 'associations': associations(root)}
    if action == 'create-passport':
        return create_passport(root, data)
    if action == 'passport-options':
        fields(data, {'registry'})
        return passport_options(root, data['registry'])
    if action == 'select-passport':
        fields(data, {'project_id', 'registry', 'passport_id'})
        choose(root, text(data['project_id']), registry=text(data['registry'], 4096), passport_id=text(data['passport_id']))
        return {'saved': True}
    if action == 'clear-passport':
        fields(data, {'project_id'})
        choose(root, text(data['project_id']))
        return {'saved': True}
    if action == 'recover':
        fields(data, {'session_id'})
        result = SessionStore(root).finish(text(data['session_id']), outcome='recovered')
        return {'session_id': result.session_id, 'outcome': result.outcome}
    raise ContractError('unknown_desktop_action')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['render', 'status', 'setup', 'pause', 'onboard', 'projects', 'create-passport', 'passport-options', 'select-passport', 'clear-passport', 'recover', 'app-status', 'app-install', 'app-repair', 'app-rollback', 'app-remove', 'usage-status', 'usage-enable', 'usage-disable', 'engagement'])
    parser.add_argument('--store', type=Path)
    args = parser.parse_args()
    try:
        root = (args.store or Path.home() / '.forkit-radar').absolute()
        value = perform(args.action, root, request())
        print(json.dumps({'ok': True, 'result': value}))
        return 0
    except (OSError, ValueError, TypeError, KeyError, subprocess.SubprocessError) as error:
        # No raw payload, project names, paths, credentials or exception text.
        messages = {
            'first_receipt_and_usage_v3_consent_required': 'Get your first receipt before enabling optional usage counts.',
            'withdraw_before_changing_usage_policy': 'Your earlier reporting consent is preserved. Withdraw it with forkit-radar usage withdraw before choosing the new policy.',
            'local_capture_busy_retry': 'Capture or a local change is finishing. Wait a moment, then try again.',
            'local_registry_unavailable': 'That local registry could not be read. Check the folder path and file access, then try again.',
            'local_passport_list_limit': 'This registry exceeds the 512-entry picker limit. Use a smaller local registry or the existing Passport CLI.',
            'mac_native_trash_failed': 'Removal could not finish. Your receipts are safe. Use Repair installation to retry the remaining app moves.',
            'native_mac_file_helper_required': 'Reopen the latest Forkit download to finish this interrupted removal.',
            'mac_trash_access_unavailable': 'macOS blocked access to Trash. Forkit and capture settings are preserved. Native removal needs further Mac validation; Full Disk Access is not required for ordinary use.',
            'mac_backup_cleanup_required': 'Older app backups need cleanup before another update. Your installed app and receipts are preserved.',
            'passport_version_format': 'Use a two- or three-part version for both Passports, such as 1.0 or 1.0.0.',
            'finish_sessions_before_mac_update': 'Finish or recover the active coding session before updating or removing Forkit.',
            'quit_installed_forkit_before_update': 'Close other Forkit windows and let its commands finish, then try again.',
            'required_metadata_missing': 'Complete all Passport fields using 1–160 characters each.',
            'finish_session_before_changing_passport': 'Finish or recover the current session before changing its Passport.',
            'project_replaced': 'This project folder was replaced. Capture a new session before choosing its Passport.',
            'consistent_local_passport_required': 'The selected registry needs a valid agent Passport and its matching model Passport.',
            'existing_mac_app_not_owned': 'An unrecognized app already uses this name. It has been preserved. Move it yourself before installing Forkit.',
            'installed_mac_app_changed': 'The installed app has changed. It has been preserved; use the reviewed original installation to recover.',
            'mac_install_disk_space': 'Free some disk space before installing. Forkit needs room for the app and its previous version.',
            'mac_update_recovery_required': 'The app update needs recovery. Reopen the same reviewed download and use Repair installation.',
            'remove_mac_hooks_needs_attention': 'A coding tool’s Forkit hooks have changed. The app was kept so those hooks do not point to a missing executable. Review Capture settings first.',
            'mac_command_changed': 'Your command-line shortcut changed during installation. It has been preserved. Restore it before retrying the update.',
            'no_previous_mac_app': 'There is no previous installed version to restore.',
        }
        message = messages.get(str(error), 'The action could not finish. Check capture settings and local file access. Your saved receipts are preserved.')
        print(json.dumps({'ok': False, 'error': message}))
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
