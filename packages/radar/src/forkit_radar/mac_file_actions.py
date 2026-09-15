"""Use the bundled Foundation helper for normal macOS Trash operations."""
from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import sys
from pathlib import Path

from .discovery.safeio import read_metadata
from .jsonio import ContractError, load_json


def helper():
    python = Path(sys.executable).resolve()
    if len(python.parents) < 5:
        return None
    app = python.parents[4]
    if python != app / 'Contents/Resources/runtime/bin/python3.11':
        return None
    marker = app / 'Contents/Resources/forkit-file-actions.json'
    if not marker.exists():  # Earlier local bundles do not carry this helper.
        return None
    data = load_json(read_metadata(marker, limit=4096))
    if set(data) != {'format', 'sha256'} or data['format'] != 1:
        raise ContractError('invalid_mac_file_helper')
    expected = data['sha256']
    path = app / 'Contents/MacOS/ForkitFileActions'
    info = path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
            or info.st_uid != os.geteuid() or info.st_mode & 0o022
            or info.st_size > 2_097_152 or hashlib.sha256(path.read_bytes()).hexdigest() != expected):
        raise ContractError('invalid_mac_file_helper')
    return path


def trash(source):
    executable = helper()
    if executable is None:
        raise ContractError('native_mac_file_helper_required')
    try:
        result = subprocess.run([str(executable)], input=json.dumps({'source': str(source)}).encode(),
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, timeout=20, check=False)
    except (OSError, subprocess.TimeoutExpired):
        # A deferred retirement must keep its journal even if the native service
        # does not respond. Never turn a successful update into an uncaught error.
        raise ContractError('mac_native_trash_failed') from None
    if len(result.stdout) > 8192:
        raise ContractError('mac_native_trash_failed')
    try:
        value = load_json(result.stdout)
    except ValueError:
        raise ContractError('mac_native_trash_failed') from None
    if not isinstance(value, dict) or result.returncode or value.get('ok') is not True or source.exists():
        raise ContractError('mac_native_trash_failed')
    return value.get('destination')
