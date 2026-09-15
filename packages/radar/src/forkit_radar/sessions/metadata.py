"""Project declarations and explicit Core association, using existing readers."""

from __future__ import annotations

import re
from pathlib import Path

from ..discovery.agents import agent_manifest
from ..discovery.mcp import _layer, _text, server_shape
from ..discovery.metadata import empty_manifest, load_metadata
from ..discovery.types import scope_keys
from ..identity.association import resolve
from ..identity.storage import canonical
from .dependencies import capture as dependencies
from .dependencies import token
from .details import Fact, Metadata, Passport, Selection, Source

KNOWN_MCP_NAMES = frozenset(
    {"playwright", "github", "filesystem", "memory", "fetch", "context7", "supabase", "stripe"}
)


def reference(value):
    # Bounded identifiers only: no URLs, queries, credentials or absolute paths.
    if (
        not isinstance(value, str)
        or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._+/-]{0,127}", value)
        or ".." in value
        or value.startswith(("sk-", "sk_", "ghp_", "github_pat_", "AIza"))
    ):
        raise ValueError("unsupported_reference")
    return value


def mcp(project, adapter, key):
    source = "codex-project-mcp" if adapter == "codex-mcp" else "cursor-project-mcp"
    path = project / (".codex/config.toml" if adapter == "codex-mcp" else ".cursor/mcp.json")
    result, entries = _layer(adapter, scope_keys(adapter)[1], path)
    facts = []
    for name, entry in entries.items():
        detail = entry.detail
        if detail.transport == "unknown":
            continue
        # A salted local slot detects replacements/reordering without retaining
        # arbitrary raw names. This is not an authenticated MCP identity.
        label = (
            f"{name} (MCP declaration)" if name in KNOWN_MCP_NAMES else "Unnamed MCP declaration"
        )
        facts.append(
            Fact(
                key=token(key, source, name),
                label=label,
                value=f"{detail.transport}; {detail.activation}",
            )
        )
    state = (
        "absent"
        if result.status == "missing"
        else "complete"
        if result.status == "complete"
        else "partial"
    )
    return Source(
        key=source,
        category="tools",
        state=state,
        reason=result.reason,
        facts=sorted(facts, key=lambda f: f.key),
    )


def claude_mcp(project, key):
    source = "claude-project-mcp"
    try:
        data = load_metadata(project / ".mcp.json")
        entries = data.get("mcpServers", {})
        if not isinstance(entries, dict):
            raise ValueError
        facts, partial = [], len(entries) > 32
        for name, value in list(entries.items())[:32]:
            try:
                if not _text(name) or len(name) > 256:
                    raise ValueError
                transport, activation = server_shape(value)
                if (
                    value.get("type") not in {None, "stdio", "http", "sse"}
                    or transport == "unknown"
                ):
                    raise ValueError
                if (
                    value.get("type") == "stdio"
                    and transport != "stdio"
                    or value.get("type") in {"http", "sse"}
                    and transport != "http"
                ):
                    raise ValueError
                label = (
                    f"{name} (MCP declaration)"
                    if name in KNOWN_MCP_NAMES
                    else "Unnamed MCP declaration"
                )
                facts.append(
                    Fact(
                        key=token(key, source, name),
                        label=label,
                        value=f"{transport}; {activation}",
                    )
                )
            except (ValueError, TypeError):
                partial = True
        return Source(
            key=source,
            category="tools",
            state="partial" if partial else "complete",
            reason="unsupported_entries" if partial else "project_declarations_approval_unknown",
            facts=sorted(facts, key=lambda f: f.key),
        )
    except FileNotFoundError:
        return Source(key=source, category="tools", state="absent", reason="not_found")
    except (OSError, ValueError, TypeError):
        return Source(
            key=source,
            category="tools",
            state="unavailable",
            reason="unreadable_or_unsupported_metadata",
        )


def model_setting(project, *, codex):
    source = "codex-project-model" if codex else "claude-project-model"
    path = project / (".codex/config.toml" if codex else ".claude/settings.json")
    try:
        data = load_metadata(path, toml=codex)
        facts, partial = [], False
        # These are project-layer declarations. User profiles, CLI overrides,
        # managed settings, sessions and chats are deliberately outside scope.
        for field in ("model", "model_provider") if codex else ("model",):
            if field in data:
                try:
                    facts.append(
                        Fact(
                            key=field,
                            label=f"{'Codex' if codex else 'Claude Code'} configured {field.replace('_', ' ')}",
                            value=reference(data[field]),
                        )
                    )
                except ValueError:
                    partial = True
        return Source(
            key=source,
            category="models",
            state="partial" if partial else "complete",
            reason="unsupported_model_reference" if partial else "project_layer_runtime_unknown",
            facts=facts,
        )
    except FileNotFoundError:
        return Source(key=source, category="models", state="absent", reason="not_found")
    except (OSError, ValueError, TypeError):
        return Source(
            key=source,
            category="models",
            state="unavailable",
            reason="unreadable_or_unsupported_metadata",
        )


def declared_manifest(selection, key):
    if selection.agent_manifest is None:
        return (), empty_manifest("agent"), None
    result = next(agent_manifest(Path(selection.agent_manifest)))
    if result.status != "complete" or len(result.candidates) != 1:
        return (
            tuple(
                Source(
                    key=f"agent-{dimension}",
                    category=category,
                    state="unavailable",
                    reason="selected_manifest_unavailable",
                )
                for dimension, category in (
                    ("tools", "tools"),
                    ("models", "models"),
                    ("settings", "configuration"),
                )
            ),
            None,
            "selected_manifest_unavailable",
        )
    manifest = result.candidates[0].manifest
    sources = []
    for dimension, category in (
        ("tools", "tools"),
        ("models", "models"),
        ("settings", "configuration"),
    ):
        status = getattr(manifest.measurement_completeness, dimension)
        facts = []
        partial = status != "complete"
        values = getattr(manifest, dimension)
        if values is not None and dimension == "settings":
            if values.origin == "unknown":
                partial = True
            else:
                for field in ("temperature", "top_p", "max_tokens"):
                    value = getattr(values, field)
                    if value is not None:
                        facts.append(Fact(key=field, label=f"Agent {field}", value=str(value)))
        elif values is not None:
            for value in values:
                slot = token(key, f"agent-{dimension}", value.key)
                if value.origin == "unknown":
                    partial = True
                    continue
                fields = ("name",) if dimension == "tools" else ("name", "version", "provider")
                for field in fields:
                    observed = getattr(value, field)
                    if observed.origin == "unknown":
                        partial = True
                        continue
                    if observed.value is not None:
                        try:
                            facts.append(
                                Fact(
                                    key=f"{slot}.{field}",
                                    label=f"Agent {'tool' if dimension == 'tools' else 'model'} {field}",
                                    value=reference(observed.value),
                                )
                            )
                        except ValueError:
                            partial = True
                if dimension == "tools":
                    if value.transport != "unknown":
                        facts.append(
                            Fact(
                                key=f"{slot}.transport",
                                label="Agent tool transport",
                                value=value.transport,
                            )
                        )
                    else:
                        partial = True
                    if value.permissions is not None:
                        facts.append(
                            Fact(
                                key=f"{slot}.permissions",
                                label="Agent tool declared permissions",
                                value=",".join(sorted(value.permissions)) or "none",
                            )
                        )
                    else:
                        partial = True
                elif value.passport_id is not None:
                    facts.append(
                        Fact(
                            key=f"{slot}.passport",
                            label="Agent model declared Passport",
                            value=value.passport_id,
                        )
                    )
        if len(facts) > 512:
            facts, partial = [], True
        sources.append(
            Source(
                key=f"agent-{dimension}",
                category=category,
                state="partial" if partial else "complete",
                reason="incomplete_declared_dimension"
                if partial
                else "explicit_manifest_declarations_only",
                facts=sorted(facts, key=lambda f: f.key),
            )
        )
    return tuple(sources), manifest, None


def association(selection, manifest, failure=None):
    if failure:
        return Passport(state="unavailable", reason=failure)
    if selection.passport_id is None and manifest.passport_id is None:
        return Passport(state="not_selected", reason="no_explicit_reference")
    result = resolve(
        manifest,
        Path(selection.registry) if selection.registry else None,
        selected_ids=(selection.passport_id,) if selection.passport_id else (),
    )
    if result.state in {"ambiguous", "conflicted"}:
        return Passport(
            state="conflicted", reason=result.reason, model_reference=result.model_reference
        )
    if len(result.candidates) != 1 or result.candidates[0].status != "consistent":
        return Passport(
            state="unavailable",
            reason="raw_valid_core_passport_unavailable",
            model_reference=result.model_reference,
        )
    check = result.candidates[0]
    return Passport(
        state="consistent",
        reason="core_id_consistent_association_declared",
        passport_id=check.passport_id,
        name=check.identity.name,
        version=check.identity.version,
        model_id=check.model_id,
        model_reference=result.model_reference,
    )


def capture(project: Path, selection: Selection, key: bytes) -> Metadata:
    sources = list(dependencies(project, key))
    sources.extend(
        (
            mcp(project, "codex-mcp", key),
            mcp(project, "cursor-mcp", key),
            claude_mcp(project, key),
            model_setting(project, codex=True),
            model_setting(project, codex=False),
        )
    )
    declared, manifest, error = declared_manifest(selection, key)
    sources.extend(declared)
    result = Metadata(
        sources=sorted(sources, key=lambda s: s.key),
        passport=association(selection, manifest, error),
    )
    if sum(len(s.facts) for s in result.sources) > 1024:
        return unavailable(result, "metadata_entry_limit", invalidate_passport=False)
    # Keep combined persisted records bounded even on extreme declarations.
    if len(canonical(result)) > 180_000:
        result = unavailable(result, "metadata_record_limit", invalidate_passport=False)
    return result


def unavailable(before: Metadata, reason: str, *, invalidate_passport=True) -> Metadata:
    return Metadata(
        sources=tuple(
            Source(key=s.key, category=s.category, state="unavailable", reason=reason)
            for s in before.sources
        ),
        passport=before.passport
        if not invalidate_passport or before.passport.state == "not_selected"
        else Passport(state="unavailable", reason=reason),
    )
