"""Metadata collectors; call through the bounded orchestrator for live scans."""

from __future__ import annotations

import errno
import plistlib
import re
import struct
import sys
import time
from collections.abc import Iterator
from pathlib import Path

from .catalog import APPLICATIONS, match_bundle, match_executable
from .safeio import MetadataError, read_metadata
from .types import Candidate, SourceResult, scope_keys

MAX_METADATA_BYTES = 65_536
MAX_PROCESSES = 4096
MAX_CANDIDATES = 128
COLLECT_SECONDS = 2.0


class _UniqueDict(dict):
    def __setitem__(self, key, value):
        if key in self:
            raise MetadataError("invalid_metadata")
        super().__setitem__(key, value)


def read_bundle_metadata(path: Path) -> dict:
    """Open each component without following symlinks, and read one small plist.

    Filesystem handles bind the read to the selected root. No recursive walk,
    executable-content read, extended attributes or bundle code loading occurs.
    """
    raw = read_metadata(path, limit=MAX_METADATA_BYTES)
    # A tiny binary plist can claim a huge object table. Bound the trailer
    # before plistlib allocates its object cache, not after parsing.
    if raw.startswith(b"bplist00"):
        if len(raw) < 40:
            raise MetadataError("invalid_metadata")
        offset_size, ref_size, objects, root_object, table = struct.unpack(">6xBBQQQ", raw[-32:])
        if (
            offset_size not in {1, 2, 4, 8}
            or ref_size not in {1, 2, 4, 8}
            or not 1 <= objects <= 2048
            or root_object >= objects
            or table < 8
            or table + offset_size * objects > len(raw) - 32
        ):
            raise MetadataError("invalid_metadata")
    try:
        parsed = plistlib.loads(raw, dict_type=_UniqueDict)
    except Exception:
        raise MetadataError("invalid_metadata") from None
    # The OS worker also enforces a deadline while parsing. Limit nested results
    # before selecting the three metadata fields; no arbitrary values escape.
    pending = [(parsed, 0)]
    count = 0
    while pending:
        value, depth = pending.pop()
        count += 1
        if depth > 16 or count > 2048:
            raise MetadataError("invalid_metadata")
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for v in value.values())
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
    if not isinstance(parsed, dict):
        raise MetadataError("invalid_metadata")
    return {
        k: parsed.get(k)
        for k in ("CFBundleIdentifier", "CFBundleExecutable", "CFBundleShortVersionString")
    }


def applications(home: Path, *, platform: str = sys.platform) -> Iterator[SourceResult]:
    deadline = time.monotonic() + COLLECT_SECONDS
    scopes = iter(scope_keys("applications"))
    for root in (Path("/Applications"), home / "Applications"):
        for product in APPLICATIONS:
            scope = next(scopes)
            status, reason, candidates = "complete", "scoped_metadata_read", ()
            if platform != "darwin":
                status, reason = "unsupported", "unsupported_platform"
            elif time.monotonic() >= deadline:
                status, reason = "timeout", "deadline_exceeded"
            else:
                try:
                    metadata = read_bundle_metadata(
                        root / product.bundle / "Contents" / "Info.plist"
                    )
                    matched = match_bundle(
                        product.bundle,
                        metadata["CFBundleIdentifier"],
                        metadata["CFBundleExecutable"],
                    )
                    if matched is None:
                        status, reason = "partial", "ambiguous_metadata"
                    else:
                        raw_version = metadata["CFBundleShortVersionString"]
                        version = (
                            raw_version
                            if isinstance(raw_version, str)
                            and re.fullmatch(r"[0-9]{1,9}(\.[0-9]{1,9}){0,3}", raw_version)
                            else None
                        )
                        candidates = (
                            Candidate(product=matched, version=version, basis="bundle_metadata"),
                        )
                except FileNotFoundError:
                    status, reason = "missing", "not_found"
                except PermissionError:
                    status, reason = "denied", "permission_denied"
                except MetadataError as exc:
                    status, reason = "partial", str(exc)
                except OSError as exc:
                    status, reason = (
                        "partial",
                        (
                            "symlink_or_unsafe_file"
                            if exc.errno in {errno.ELOOP, errno.ENOTDIR}
                            else "collector_failed"
                        ),
                    )
            yield SourceResult(scope=scope, status=status, reason=reason, candidates=candidates)


def processes(*, platform: str = sys.platform) -> Iterator[SourceResult]:
    scope = scope_keys("processes")[0]
    if platform not in {"darwin", "linux"}:
        yield SourceResult(
            scope=scope, status="unsupported", reason="unsupported_platform", candidates=()
        )
        return
    try:
        import psutil
    except ImportError:
        yield SourceResult(
            scope=scope, status="unsupported", reason="dependency_unavailable", candidates=()
        )
        return

    class ExecutableOnlyProcess(psutil.Process):
        # psutil 7.2.2 exe() guesses from cmdline on native denial/empty results.
        # Block that fallback before collection, rather than redacting later.
        def cmdline(self):
            raise psutil.AccessDenied()

        def environ(self):
            raise psutil.AccessDenied()

    deadline = time.monotonic() + COLLECT_SECONDS
    candidates = []
    status, reason = "complete", "process_table_read"
    try:
        pids = psutil.pids()
        for index, pid in enumerate(pids):
            if index >= MAX_PROCESSES:
                status, reason = "partial", "entry_limit"
                break
            if time.monotonic() >= deadline:
                status, reason = "partial", "deadline_exceeded"
                break
            try:
                executable = ExecutableOnlyProcess(pid).exe()
                if not executable:
                    status, reason = "partial", "process_visibility_limited"
                    continue
                match = match_executable(executable)
                if match:
                    if len(candidates) >= MAX_CANDIDATES:
                        status, reason = "partial", "result_limit"
                        break
                    candidates.append(
                        Candidate(
                            product=match[0],
                            version=None,
                            basis="ambiguous_executable"
                            if match[0] == "chatgpt-or-codex"
                            else "executable_metadata",
                        )
                    )
            except (psutil.AccessDenied, psutil.NoSuchProcess):
                status, reason = "partial", "process_visibility_limited"
            except OSError:
                status, reason = "partial", "process_visibility_limited"
    except (psutil.Error, OSError):
        status, reason = "denied", "process_table_unavailable"
        candidates = []
    yield SourceResult(scope=scope, status=status, reason=reason, candidates=candidates)
