"""Bounded local setup files, private backups and guarded atomic replacement."""
from __future__ import annotations

import fcntl
import hashlib
import os
import stat
from contextlib import contextmanager
from uuid import uuid4

from ..discovery.safeio import directory, read_at
from ..jsonio import ContractError


def digest(raw):
    return None if raw is None else hashlib.sha256(raw).hexdigest()


def private_directory(path):
    with directory(path.parent) as parent:
        try:
            os.mkdir(path.name, mode=0o700, dir_fd=parent)
        except FileExistsError:
            pass
    with directory(path) as fd:
        info = os.fstat(fd)
        if info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o700:
            raise ContractError('private_setup_directory_required')


def read(path, *, private=False):
    try:
        with directory(path.parent) as parent:
            info = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
            if info.st_uid != os.geteuid() or info.st_mode & 0o022:
                raise ContractError('unsafe_setup_file_permissions')
            if private and stat.S_IMODE(info.st_mode) != 0o600:
                raise ContractError('private_setup_file_required')
            return read_at(parent, path.name, 1_048_576 if private else 65_536)
    except FileNotFoundError:
        return None


def replace(path, raw, *, expected):
    """Check the observed bytes again; preserve unrelated edits and reject links.

    The lock serializes Forkit writers. Other tools do not honor that lock;
    the final stat/read check detects changes up to the atomic replacement.
    It is not an OS compare-and-swap against a hostile same-user process.
    """
    if raw is not None and len(raw) > 1_048_576:
        raise ContractError('setup_file_too_large')
    with directory(path.parent) as parent:
        info = os.fstat(parent)
        if info.st_uid != os.geteuid() or info.st_mode & 0o022:
            raise ContractError('unsafe_setup_parent_permissions')
        if read(path) != expected:
            raise ContractError('setup_file_changed_retry')
        if raw is None:
            if expected is not None:
                os.unlink(path.name, dir_fd=parent)
                os.fsync(parent)
            return
        temp = '.forkit-setup-' + str(uuid4())
        fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent)
        try:
            with os.fdopen(fd, 'wb') as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            if read(path) != expected:
                raise ContractError('setup_file_changed_retry')
            if expected is None:
                os.link(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
            else:
                os.replace(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent)
            os.fsync(parent)
        finally:
            try:
                os.unlink(temp, dir_fd=parent)
            except FileNotFoundError:
                pass


def open_lock_file(parent, name):
    # On this Mac, simultaneous O_CREAT opens of a new name can return ENOENT.
    # Elect one creator, then reopen the existing inode without creation flags.
    flags = os.O_RDWR | os.O_NOFOLLOW | os.O_NONBLOCK
    try:
        return os.open(name, flags | os.O_CREAT | os.O_EXCL, 0o600, dir_fd=parent)
    except FileExistsError:
        return os.open(name, flags, dir_fd=parent)


@contextmanager
def locked(root):
    private_directory(root)
    with directory(root) as parent:
        fd = open_lock_file(parent, 'setup.lock')
        try:
            info = os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1 or info.st_uid != os.geteuid() or stat.S_IMODE(info.st_mode) != 0o600:
                raise ContractError('unsafe_setup_lock')
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                raise ContractError('setup_busy_retry') from None
            yield
        finally:
            os.close(fd)
