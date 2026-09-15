"""Shared builders: metadata declarations cannot establish trust or identity."""

from __future__ import annotations

import errno
from datetime import date, datetime, time
from decimal import Decimal
from uuid import uuid4

from ..contracts import Manifest
from ..jsonio import MAX_SAFE_INTEGER, ContractError, load_json
from .safeio import MetadataError, read_metadata
from .types import MetadataCandidate, MetadataDetail, SourceResult

MAX_ENTRIES = 32


def empty_manifest(kind: str, *, dimensions=("identity",)) -> Manifest:
    unknown = {"value": None, "origin": "unknown"}
    return Manifest.model_validate(
        {
            "schema_version": "1.0",
            "logical_agent_id": None,
            "provisional_component_key": str(uuid4()),
            "passport_id": None,
            "component_kind": kind,
            "scope_profile": {
                "profile_id": "passive-metadata-v1",
                "normalization_version": "1",
                "dimensions": list(dimensions),
            },
            "declared_identity": {
                k: unknown for k in ("name", "version", "creator", "organization")
            },
            "tools": None,
            "models": None,
            "artifacts": None,
            "settings": None,
            "measurement_completeness": {
                k: "unsupported" if k in dimensions else "not_selected"
                for k in ("identity", "tools", "models", "artifacts", "settings")
            },
        }
    )


def candidate(
    adapter: str,
    index: int,
    *,
    manifest: Manifest | None = None,
    transport=None,
    activation=None,
    precedence="layer_only",
    declared_bytes=None,
):
    if manifest is None:
        kind = "mcp_server" if adapter.endswith("-mcp") else "agent"
        dimensions = (
            ("identity", "tools")
            if kind == "mcp_server"
            else ("identity", "tools", "models", "settings")
        )
        manifest = empty_manifest(kind, dimensions=dimensions)
    return MetadataCandidate(
        manifest=manifest,
        detail=MetadataDetail(
            adapter=adapter,
            entry_index=index,
            transport=transport,
            activation=activation,
            precedence=precedence,
            declared_bytes=declared_bytes,
        ),
    )


def failure(scope: str, exc: Exception) -> SourceResult:
    if isinstance(exc, FileNotFoundError):
        status, reason = "missing", "not_found"
    elif isinstance(exc, PermissionError):
        status, reason = "denied", "permission_denied"
    elif isinstance(exc, ImportError):
        status, reason = "unsupported", "dependency_unavailable"
    elif isinstance(exc, MetadataError):
        status, reason = "partial", str(exc)
    elif isinstance(exc, OSError) and exc.errno in {errno.ELOOP, errno.ENOTDIR}:
        status, reason = "partial", "symlink_or_unsafe_file"
    else:
        status, reason = "malformed", "invalid_metadata"
    return SourceResult(scope=scope, status=status, reason=reason, candidates=())


def load_metadata(path, *, toml=False):
    raw = read_metadata(path)
    if not toml:
        return load_json(raw)
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    try:
        parsed = tomllib.loads(raw.decode("utf-8"), parse_float=Decimal)
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("invalid_metadata") from None
    # TOML's typed dates and finite decimals may occur in unrelated client
    # settings. Bound them without reserializing or exposing those values.
    pending = [(parsed, 0)]
    nodes = 0
    while pending:
        value, depth = pending.pop()
        nodes += 1
        if nodes > 20_000 or depth > 32:
            raise ContractError("invalid_metadata")
        if isinstance(value, dict):
            pending.extend((v, depth + 1) for pair in value.items() for v in pair)
        elif isinstance(value, list):
            pending.extend((v, depth + 1) for v in value)
        elif isinstance(value, str):
            value.encode("utf-8", errors="strict")
        elif isinstance(value, bool) or isinstance(value, (date, datetime, time)):
            pass
        elif isinstance(value, int):
            if abs(value) > MAX_SAFE_INTEGER:
                raise ContractError("invalid_metadata")
        elif isinstance(value, Decimal):
            if not value.is_finite():
                raise ContractError("invalid_metadata")
        else:
            raise ContractError("invalid_metadata")
    return parsed
