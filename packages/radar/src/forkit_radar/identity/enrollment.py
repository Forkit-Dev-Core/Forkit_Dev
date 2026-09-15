"""Explicit source selection and unsigned enrollment drafts, never active bindings."""

import unicodedata
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, model_validator

from ..contracts import UTC, Contract, Entries, Identifier, Manifest, Text, Token
from ..discovery.agents import _python_graph_reference, agent_manifest
from ..discovery.metadata import empty_manifest, load_metadata
from ..jsonio import ContractError
from .association import Association, resolve


class Locator(Contract):
    adapter: Literal["agent-manifest", "langgraph"]
    # This type is PRIVATE storage only, never embedded in a Manifest or export.
    path: str
    selector: Text | None

    @model_validator(mode="after")
    def exact_source(self):
        path = Path(self.path)
        if (
            not path.is_absolute()
            or ".." in path.parts
            or len(path.parts) > 16
            or len(self.path) > 4096
            or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in self.path)
        ):
            raise ValueError("unsafe_source_path")
        if (self.adapter == "langgraph") != (self.selector is not None):
            raise ValueError("invalid_source_selector")
        return self


class EnrollmentPreview(Contract):
    manifest: Manifest
    association: Association
    blockers: Entries[Token]
    authority: Literal["unavailable"] = "unavailable"
    acceptance: Literal["unreviewed"] = "unreviewed"

    @model_validator(mode="after")
    def unsigned_agent_only(self):
        if self.manifest.component_kind != "agent" or self.manifest.logical_agent_id is not None:
            raise ValueError("unbound_agent_required")
        if not {"authority_unavailable", "revision_not_prepared"}.issubset(self.blockers):
            raise ValueError("pending_prerequisites_required")
        pending = [self.manifest.model_dump()]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if "origin" in value and value["origin"] not in {"declared", "unknown"}:
                    raise ValueError("unverified_draft_metadata")
                pending.extend(value.values())
            elif isinstance(value, (list, tuple)):
                pending.extend(value)
        return self


class EnrollmentDraft(Contract):
    schema_version: Literal["1.0"]
    proposal_id: Identifier
    reserved_logical_agent_id: Identifier
    source_slot_id: Identifier
    created_at: UTC
    preview: EnrollmentPreview
    revision_digest: None = None
    accepted_binding_digest: None = None
    authority_id: None = None


class EnrollmentEntry(Contract):
    state: Literal["pending", "cancelled"]
    draft: EnrollmentDraft


def select_source(
    *, agent_file: Path | None = None, project: Path | None = None, graph_key: str | None = None
) -> tuple[Locator, Manifest]:
    if (agent_file is None) == (project is None):
        raise ContractError("select_exactly_one_agent_source")
    if agent_file is not None:
        if graph_key is not None:
            raise ContractError("unexpected_graph_selector")
        locator = Locator(adapter="agent-manifest", path=str(agent_file.absolute()), selector=None)
        result = next(agent_manifest(Path(locator.path)))
        if result.status != "complete" or len(result.candidates) != 1:
            raise ContractError("agent_source_unavailable")
        return locator, result.candidates[0].manifest
    if graph_key is None:
        raise ContractError("explicit_graph_key_required")
    TypeAdapter(Text).validate_python(graph_key, strict=True)
    locator = Locator(
        adapter="langgraph", path=str((project / "langgraph.json").absolute()), selector=graph_key
    )
    try:
        data = load_metadata(Path(locator.path))
        graphs = data.get("graphs")
        if (
            not isinstance(graphs, dict)
            or graph_key not in graphs
            or not _python_graph_reference(graphs[graph_key])
        ):
            raise ValueError
    except (OSError, ValueError, TypeError):
        raise ContractError("selected_graph_unavailable") from None
    return locator, empty_manifest("agent", dimensions=("identity", "tools", "models", "settings"))


def preview(
    manifest: Manifest, *, registry: Path | None = None, passport_ids=()
) -> EnrollmentPreview:
    association = resolve(manifest, registry, selected_ids=passport_ids)
    blockers = ["authority_unavailable", "revision_not_prepared"]
    if association.state in {"ambiguous", "conflicted"}:
        blockers.append("association_unresolved")
    if not association.candidates or association.candidates[0].status != "consistent":
        blockers.append("passport_not_checked")
    if association.model_reference != "consistent":
        blockers.append("model_reference_not_checked")
    if any(
        getattr(manifest.declared_identity, key).value is None
        for key in ("name", "version", "creator")
    ):
        blockers.append("identity_metadata_incomplete")
    return EnrollmentPreview(manifest=manifest, association=association, blockers=blockers)
