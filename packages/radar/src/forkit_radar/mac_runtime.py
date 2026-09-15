"""Locate the app's shipped Git, without consulting project config or PATH."""
from __future__ import annotations

import hashlib
import sys
from functools import lru_cache
from pathlib import Path

from .discovery.safeio import read_metadata
from .jsonio import ContractError, load_json


@lru_cache(maxsize=1)
def bundled_git():
    root = Path(sys.executable).resolve(strict=True).parent.parent
    marker = root / 'forkit-runtime.json'
    if sys.platform != 'darwin' or not marker.exists():
        return None
    data = load_json(read_metadata(marker, limit=4096))
    if set(data) != {'format', 'git_sha256'} or data['format'] != 1:
        raise ContractError('invalid_bundled_runtime')
    path = root.parent / 'git/bin/git'
    binary = read_metadata(path, limit=33_554_432)
    if hashlib.sha256(binary).hexdigest() != data['git_sha256']:
        raise ContractError('bundled_git_changed')
    return str(path)
