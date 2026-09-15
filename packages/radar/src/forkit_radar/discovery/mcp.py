"""Passive Codex/Cursor MCP declarations. No expansion, lookup or connection."""

from __future__ import annotations

import time
import unicodedata
from pathlib import Path

from ..jsonio import ContractError
from .metadata import MAX_ENTRIES, candidate, failure, load_metadata
from .types import MetadataCandidate, SourceResult, scope_keys


def _text(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 4096
        and not any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)
    )


def server_shape(data, *, codex_enabled=False):
    """Validate shared MCP transport declarations without retaining raw values."""
    if not isinstance(data, dict):
        raise ContractError("invalid_metadata")
    command, url = data.get("command"), data.get("url")
    if "command" in data and not _text(command) or "url" in data and not _text(url):
        raise ContractError("invalid_metadata")
    if command is not None and url is not None:
        raise ContractError("invalid_metadata")
    transport = "stdio" if command is not None else "http" if url is not None else "unknown"
    activation = "unknown"
    if codex_enabled:
        if "enabled" in data and type(data["enabled"]) is not bool:
            raise ContractError("invalid_metadata")
        activation = "enabled" if data.get("enabled", True) else "disabled"
    return transport, activation


def _server(adapter, index, data):
    transport, activation = server_shape(data, codex_enabled=adapter == "codex-mcp")
    # No command, arguments, URL, headers, env names/values, server/tool names,
    # interpolated variables or raw config digests cross this ingestion boundary.
    return candidate(
        adapter, index, transport=transport, activation=activation
    ), transport != "unknown"


def _layer(adapter, scope, path):
    if path is None:
        return SourceResult(
            scope=scope, status="unsupported", reason="project_not_selected", candidates=()
        ), {}
    try:
        data = load_metadata(path, toml=adapter == "codex-mcp")
        servers = data.get("mcp_servers" if adapter == "codex-mcp" else "mcpServers", {})
        if not isinstance(servers, dict):
            raise ContractError("invalid_metadata")
        found, unknown = {}, 0
        status, reason = "complete", "scoped_metadata_read"
        deadline = time.monotonic() + 2
        for index, (name, entry) in enumerate(servers.items(), 1):
            if index > MAX_ENTRIES or time.monotonic() >= deadline:
                unknown += len(servers) - index + 1
                status, reason = (
                    "partial",
                    "entry_limit" if index > MAX_ENTRIES else "deadline_exceeded",
                )
                break
            try:
                if not _text(name) or len(name) > 256:
                    raise ContractError("invalid_metadata")
                value, complete = _server(adapter, index, entry)
                found[name] = value
                if not complete:
                    unknown += 1
                    status, reason = "partial", "entry_invalid"
            except (ValueError, TypeError):
                unknown += 1
                status, reason = "partial", "entry_invalid"
        return SourceResult(
            scope=scope,
            status=status,
            reason=reason,
            candidates=tuple(found.values()),
            unknown_entries=min(unknown, 4096),
        ), found
    except Exception as exc:
        return failure(scope, exc), {}


def _qualify(value: MetadataCandidate, precedence):
    raw = value.model_dump()
    raw["detail"]["precedence"] = precedence
    return MetadataCandidate.model_validate(raw)


def codex(home: Path, project: Path | None = None, *, codex_home: Path | None = None):
    scopes = scope_keys("codex-mcp")
    paths = (
        (codex_home or home / ".codex") / "config.toml",
        project / ".codex/config.toml" if project is not None else None,
    )
    for index, (scope, path) in enumerate(zip(scopes, paths, strict=True)):
        result, _ = _layer("codex-mcp", scope, path)
        raw = result.model_dump()
        raw["candidates"] = [
            _qualify(c, "project_trust_unknown" if index else "layer_only").model_dump()
            for c in result.candidates
        ]
        # CLI/profile, system, managed settings and plugins are outside scope.
        # Selecting a project for Radar does not trust/enable it in Codex.
        yield SourceResult.model_validate(raw)


def cursor(home: Path, project: Path | None = None):
    scopes = scope_keys("cursor-mcp")
    user, user_entries = _layer("cursor-mcp", scopes[0], home / ".cursor/mcp.json")
    local, local_entries = _layer(
        "cursor-mcp", scopes[1], project / ".cursor/mcp.json" if project else None
    )
    comparable = user.status in {"complete", "missing"} and (
        project is None or local.status in {"complete", "missing"}
    )
    for result, entries, is_user in ((user, user_entries, True), (local, local_entries, False)):
        qualified = []
        for name, value in entries.items():
            precedence = (
                "unresolved"
                if not comparable
                else ("shadowed" if is_user and name in local_entries else "selected_sources_only")
            )
            qualified.append(_qualify(value, precedence))
        raw = result.model_dump()
        raw["candidates"] = [c.model_dump() for c in qualified]
        if not comparable and result.status == "complete":
            raw.update(status="partial", reason="precedence_unresolved")
        yield SourceResult.model_validate(raw)
