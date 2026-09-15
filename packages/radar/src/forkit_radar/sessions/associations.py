"""Explicit local Passport choices for automatically captured Git projects.

Uses the existing SessionStore project binding and Core registry. Choosing an
identity is optional; installation and a first receipt do not require this file.
"""
from __future__ import annotations

import hashlib
import hmac
import os
from pathlib import Path

from ..capture import setup_files as files
from ..identity.passports import lookup
from ..jsonio import ContractError, load_json
from ..lifecycle import maintenance
from .details import Selection
from .inventory import select_project
from .storage import ProjectLocator, SessionStore, checked_bytes, read

NAME = 'session-associations.json'


def projects(store):
    try:
        with store._connect() as db:
            rows = db.execute('SELECT project_id, locator_token, locator FROM projects ORDER BY rowid DESC LIMIT 1001').fetchall()
            if len(rows) > 1000:
                raise ContractError('project_list_limit')
            key = store._key(db)
            result = []
            for project_id, token, raw in rows:
                locator = read(ProjectLocator, raw)
                expected = hmac.new(key, b'forkit-session-project-v1\n' + checked_bytes(locator), hashlib.sha256).hexdigest()
                if not hmac.compare_digest(token, expected):
                    raise ContractError('project_binding_conflict')
                result.append({'project_id': project_id, **locator.model_dump(), 'name': Path(locator.path).name})
            return result
    except FileNotFoundError:
        return []


def associations(root):
    raw = files.read(root / NAME, private=True)
    value = load_json(raw) if raw else {'format': 1, 'projects': {}}
    if set(value) != {'format', 'projects'} or value['format'] != 1 or type(value['projects']) is not dict or len(value['projects']) > 1000:
        raise ContractError('invalid_local_associations')
    for item in value['projects'].values():
        if type(item) is not dict or set(item) != {'locator', 'selection'}:
            raise ContractError('invalid_local_association')
        ProjectLocator.model_validate(item['locator'])
        Selection.model_validate(item['selection'])
    return value


def selection_for(root, project):
    data = associations(root)
    if not data['projects']:
        return Selection()
    # The caller has already selected the physical Git root. Check its current
    # inode as well as its path so replacement/cloning never inherits a choice.
    from ..discovery.safeio import directory
    with directory(project) as fd:
        info = os.fstat(fd)
    matches = [item for item in data['projects'].values()
               if item['locator'] == {'path': str(project), 'device': info.st_dev, 'inode': info.st_ino}]
    if len(matches) > 1:
        raise ContractError('ambiguous_local_association')
    return Selection.model_validate(matches[0]['selection']) if matches else Selection()


def checked_project(root, project_id):
    store = SessionStore(root)
    selected = next((p for p in projects(store) if p['project_id'] == project_id), None)
    if selected is None:
        raise ContractError('unknown_local_project')
    project, identity = select_project(Path(selected['path']))
    if identity != (selected['device'], selected['inode']):
        raise ContractError('project_replaced')
    if store.active_in(project):
        raise ContractError('finish_session_before_changing_passport')
    return project, identity


@maintenance
def choose(root, project_id, *, registry=None, passport_id=None):
    from ..capture.automatic import encode
    project, identity = checked_project(root, project_id)
    if passport_id is not None:
        check = lookup(Path(registry), passport_id, kind='agent')
        if check.status != 'consistent' or lookup(Path(registry), check.model_id, kind='model').status != 'consistent':
            raise ContractError('consistent_local_passport_required')
    with files.locked(root):
        value = associations(root)
        if passport_id is None:
            value['projects'].pop(project_id, None)
        else:
            value['projects'][project_id] = {
                'locator': {'path': str(project), 'device': identity[0], 'inode': identity[1]},
                'selection': Selection(registry=str(Path(registry).absolute()), passport_id=passport_id).model_dump(),
            }
        path = root / NAME
        raw = encode(value)
        if len(raw) > 65_536:
            raise ContractError('local_association_limit')
        files.replace(path, raw, expected=files.read(path, private=True))
