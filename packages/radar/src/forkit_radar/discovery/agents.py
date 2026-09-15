"""Explicit LangGraph project and Radar manifest readers. Never import the agent."""

from __future__ import annotations

import re
import time
from pathlib import Path
from uuid import uuid4

from ..contracts import Manifest, read_contract
from ..jsonio import ContractError
from .metadata import MAX_ENTRIES, candidate, failure, load_metadata
from .safeio import read_metadata
from .types import SourceResult, scope_keys


def _python_graph_reference(value):
    if not isinstance(value, str) or len(value) > 1024 or ":" not in value:
        return False
    module, symbol = value.rsplit(":", 1)
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", symbol):
        return False
    if module.startswith("./"):
        module = module[2:]
    if module.endswith(".py"):
        return bool(re.fullmatch(r"[A-Za-z0-9_-]+(?:/[A-Za-z0-9_-]+)*\.py", module))
    if module.endswith((".js", ".ts", ".mjs", ".cjs", ".tsx", ".jsx", ".json")):
        return False
    return bool(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*", module))


def langgraph(project: Path | None):
    scope = scope_keys("langgraph")[0]
    if project is None:
        yield SourceResult(
            scope=scope, status="unsupported", reason="project_not_selected", candidates=()
        )
        return
    try:
        data = load_metadata(project / "langgraph.json")
        graphs = data.get("graphs")
        if not isinstance(graphs, dict):
            raise ContractError("invalid_metadata")
        found, unknown = [], 0
        deadline = time.monotonic() + 2
        reason = "scoped_metadata_read"
        for index, reference in enumerate(graphs.values(), 1):
            if index > MAX_ENTRIES or time.monotonic() >= deadline:
                unknown += len(graphs) - index + 1
                reason = "entry_limit" if index > MAX_ENTRIES else "deadline_exceeded"
                break
            if not _python_graph_reference(reference):
                unknown += 1
                reason = "entry_invalid"
                continue
            found.append(candidate("langgraph", index))
        yield SourceResult(
            scope=scope,
            status="partial" if unknown else "complete",
            reason=reason,
            candidates=found,
            unknown_entries=min(unknown, 4096),
        )
    except Exception as exc:
        yield failure(scope, exc)


def agent_manifest(path: Path | None):
    scope = scope_keys("agent-manifest")[0]
    if path is None:
        yield SourceResult(
            scope=scope, status="unsupported", reason="manifest_not_selected", candidates=()
        )
        return
    try:
        manifest = read_contract("manifest", read_metadata(path))
        if manifest.component_kind != "agent":
            raise ContractError("invalid_metadata")
        raw = manifest.model_dump()
        raw["logical_agent_id"] = None
        raw["provisional_component_key"] = str(uuid4())
        if raw["scope_profile"]["profile_id"] != "passive-metadata-v1":
            raise ContractError("invalid_metadata")
        pending = [raw]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if "origin" in value and value["origin"] != "unknown":
                    value["origin"] = "declared"
                pending.extend(value.values())
            elif isinstance(value, (tuple, list)):
                pending.extend(value)
        # A copied logical ID/key or independently_measured label is not trusted.
        # An explicit Passport reference remains a declaration until S05 checks it.
        found = candidate("agent-manifest", 1, manifest=Manifest.model_validate(raw))
        yield SourceResult(
            scope=scope, status="complete", reason="scoped_metadata_read", candidates=(found,)
        )
    except Exception as exc:
        yield failure(scope, exc)
