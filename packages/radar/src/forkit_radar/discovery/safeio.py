"""Small metadata files and directory handles, never source or credential loading."""

from __future__ import annotations

import os
import stat
import unicodedata
from contextlib import contextmanager
from pathlib import Path


class MetadataError(ValueError):
    """Fixed, non-disclosing collector error code."""


@contextmanager
def directory(path: Path):
    if (
        not path.is_absolute()
        or len(path.parts) > 16
        or ".." in path.parts
        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in str(path))
    ):
        raise MetadataError("symlink_or_unsafe_file")
    descriptor = os.open(path.anchor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        for part in path.parts[1:]:
            child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=descriptor)
            os.close(descriptor)
            descriptor = child
        yield descriptor
    finally:
        os.close(descriptor)


def read_at(parent: int, name: str, limit: int) -> bytes:
    if name in {"", ".", ".."} or "/" in name:
        raise MetadataError("symlink_or_unsafe_file")
    descriptor = os.open(name, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=parent)
    with os.fdopen(descriptor, "rb") as source:
        before = os.fstat(source.fileno())
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
            raise MetadataError("symlink_or_unsafe_file")
        if before.st_size > limit:
            raise MetadataError("metadata_too_large")
        raw = source.read(limit + 1)
        after = os.fstat(source.fileno())
        located = os.stat(name, dir_fd=parent, follow_symlinks=False)
        fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
        if any(
            getattr(before, f) != getattr(check, f) for check in (after, located) for f in fields
        ):
            raise MetadataError("metadata_changed")
    if len(raw) > limit:
        raise MetadataError("metadata_too_large")
    return raw


def read_metadata(path: Path, *, limit: int = 65_536) -> bytes:
    if len(path.parts) > 16 or not path.name:
        raise MetadataError("symlink_or_unsafe_file")
    with directory(path.parent) as parent:
        return read_at(parent, path.name, limit)
