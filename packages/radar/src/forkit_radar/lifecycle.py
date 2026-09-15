"""Coordinate local capture with setup, Passport selection and Mac maintenance.

Shared capture locks allow independent worktrees to run together. Maintenance
uses an exclusive, nonblocking lock: it asks for a retry instead of consuming a
coding tool's hook timeout. Journals keep interrupted Mac changes visible after
the OS releases a dead process's lock. This coordinates cooperating Forkit code,
not older runtimes or arbitrary same-user writers.
"""
from __future__ import annotations

import fcntl
import os
import stat
import threading
from contextlib import contextmanager
from functools import wraps

from .capture import setup_files as files
from .discovery.safeio import directory
from .jsonio import ContractError

_HELD = threading.local()
_JOURNALS = ('mac-install-transaction.json', 'mac-removal.json')


@contextmanager
def guard(root, *, exclusive=False):
    files.private_directory(root)
    with directory(root) as parent:
        info = os.fstat(parent)
        key = (os.getpid(), info.st_dev, info.st_ino)
        held = getattr(_HELD, 'locks', None)
        if held is None:
            held = _HELD.locks = {}
        if key in held:
            # Nest only within the same operation type. Never upgrade a reader
            # or accidentally begin capture inside a maintenance operation.
            if held[key] != exclusive:
                raise ContractError('local_capture_busy_retry')
            yield
            return
        fd = files.open_lock_file(parent, 'lifecycle.lock')
        try:
            info = os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or info.st_nlink != 1
                    or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600):
                raise ContractError('unsafe_lifecycle_lock')
            try:
                fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContractError('local_capture_busy_retry') from None
            if not exclusive:
                for name in _JOURNALS:
                    if files.read(root / name, private=True) is not None:
                        raise ContractError('mac_update_recovery_required')
            held[key] = exclusive
            try:
                yield
            finally:
                del held[key]
        finally:
            os.close(fd)


def maintenance(function):
    @wraps(function)
    def operation(root, *args, **kwargs):
        with guard(root, exclusive=True):
            return function(root, *args, **kwargs)
    return operation


def session_operation(function):
    @wraps(function)
    def operation(store, *args, **kwargs):
        with guard(store.root):
            return function(store, *args, **kwargs)
    return operation
