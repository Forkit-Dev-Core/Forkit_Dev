"""Internal allowlisted collector results and private, ephemeral scan reports."""

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import (
    UTC,
    Contract,
    Counter,
    Entries,
    EvidenceState,
    Identifier,
    Manifest,
    Observation,
)
from ..identity.association import Association
from .catalog import PRODUCT_NAMES

Detector = Literal[
    "applications", "processes", "codex-mcp", "cursor-mcp", "ollama", "langgraph", "agent-manifest"
]
DETECTORS = (
    "applications",
    "processes",
    "codex-mcp",
    "cursor-mcp",
    "ollama",
    "langgraph",
    "agent-manifest",
)
DEFAULT_DETECTORS = ("applications", "processes", "codex-mcp", "cursor-mcp", "ollama")
Status = Literal["complete", "partial", "denied", "missing", "unsupported", "timeout", "malformed"]
Reason = Literal[
    "scoped_metadata_read",
    "not_found",
    "permission_denied",
    "unsupported_platform",
    "symlink_or_unsafe_file",
    "metadata_too_large",
    "metadata_changed",
    "invalid_metadata",
    "ambiguous_metadata",
    "deadline_exceeded",
    "entry_limit",
    "result_limit",
    "process_table_read",
    "process_visibility_limited",
    "process_table_unavailable",
    "collector_failed",
    "invalid_worker_output",
    "worker_output_limit",
    "dependency_unavailable",
    "project_not_selected",
    "manifest_not_selected",
    "entry_invalid",
    "precedence_unresolved",
]
Version = Annotated[str, Field(pattern=r"^[0-9]{1,9}(\.[0-9]{1,9}){0,3}$", max_length=39)]


class Candidate(Contract):
    product: str
    version: Version | None
    basis: Literal["bundle_metadata", "executable_metadata", "ambiguous_executable"]

    @model_validator(mode="after")
    def supported_product(self):
        if self.product not in PRODUCT_NAMES:
            raise ValueError("unsupported_product")
        if (self.product == "chatgpt-or-codex") != (self.basis == "ambiguous_executable"):
            raise ValueError("ambiguous_product_requires_qualified_basis")
        return self


class MetadataDetail(Contract):
    adapter: Literal["codex-mcp", "cursor-mcp", "ollama", "langgraph", "agent-manifest"]
    entry_index: Annotated[int, Field(ge=1, le=32)]
    transport: Literal["stdio", "http", "unknown"] | None
    activation: Literal["enabled", "disabled", "unknown"] | None
    precedence: Literal[
        "layer_only", "selected_sources_only", "shadowed", "unresolved", "project_trust_unknown"
    ]
    declared_bytes: Counter | None

    @model_validator(mode="after")
    def adapter_fields(self):
        if self.adapter.endswith("-mcp"):
            if self.transport is None or self.activation is None or self.declared_bytes is not None:
                raise ValueError("invalid_mcp_detail")
            allowed = (
                {"layer_only", "project_trust_unknown"}
                if self.adapter == "codex-mcp"
                else {"selected_sources_only", "shadowed", "unresolved", "layer_only"}
            )
            if self.precedence not in allowed:
                raise ValueError("unsupported_precedence")
            if self.adapter == "cursor-mcp" and self.activation != "unknown":
                raise ValueError("unobserved_cursor_activation")
        elif (
            self.transport is not None
            or self.activation is not None
            or self.precedence != "layer_only"
            or (self.adapter != "ollama" and self.declared_bytes is not None)
        ):
            raise ValueError("invalid_metadata_detail")
        if self.adapter == "ollama" and self.declared_bytes is None:
            raise ValueError("missing_declared_size")
        return self


class MetadataCandidate(Contract):
    manifest: Manifest
    detail: MetadataDetail

    @model_validator(mode="after")
    def no_automatic_identity_or_measurement(self):
        if self.manifest.logical_agent_id is not None:
            raise ValueError("no_enrollment_from_metadata")
        if self.manifest.scope_profile.profile_id != "passive-metadata-v1":
            raise ValueError("passive_scope_required")
        if self.detail.adapter != "agent-manifest" and self.manifest.passport_id is not None:
            raise ValueError("no_inferred_passport")
        expected = {
            "codex-mcp": "mcp_server",
            "cursor-mcp": "mcp_server",
            "ollama": "model",
            "langgraph": "agent",
            "agent-manifest": "agent",
        }
        if self.manifest.component_kind != expected[self.detail.adapter]:
            raise ValueError("invalid_adapter_kind")
        if self.detail.adapter != "agent-manifest":
            if any(
                v.origin != "unknown" for v in self.manifest.declared_identity.__dict__.values()
            ):
                raise ValueError("automatic_private_names_forbidden")
            if any(getattr(self.manifest, k) is not None for k in ("tools", "models", "settings")):
                raise ValueError("unobserved_configuration_fields")
            if self.detail.adapter != "ollama" and self.manifest.artifacts is not None:
                raise ValueError("unobserved_artifacts")
            if self.detail.adapter == "ollama":
                artifacts = self.manifest.artifacts
                if (
                    not artifacts
                    or len(artifacts) > 4
                    or any(
                        a.key != f"model-layer-{i}"
                        or a.kind != "file"
                        or a.hashing_profile != "unknown"
                        or a.digest.origin != "declared"
                        or a.digest.value is None
                        for i, a in enumerate(artifacts, 1)
                    )
                ):
                    raise ValueError("invalid_model_descriptors")
        pending = [self.manifest.model_dump()]
        while pending:
            value = pending.pop()
            if isinstance(value, dict):
                if "origin" in value and value["origin"] not in {"unknown", "declared"}:
                    raise ValueError("unmeasured_metadata")
                pending.extend(value.values())
            elif isinstance(value, (tuple, list)):
                pending.extend(value)
        return self


class SourceResult(Contract):
    # Scope keys come from the collector's finite catalog, not private paths.
    scope: str
    status: Status
    reason: Reason
    candidates: Entries[Candidate | MetadataCandidate]
    unknown_entries: Annotated[int, Field(ge=0, le=4096)] = 0

    @model_validator(mode="after")
    def bounded_source(self):
        if self.scope not in tuple(s for d in DETECTORS for s in scope_keys(d)):
            raise ValueError("unsupported_scope")
        if self.status not in {"complete", "partial"} and self.candidates:
            raise ValueError("failed_source_has_no_candidates")
        if self.status == "complete" and self.unknown_entries:
            raise ValueError("unknown_entries_are_incomplete")
        if len(self.candidates) > 128:
            raise ValueError("result_limit")
        if self.scope not in scope_keys("applications") + scope_keys("processes"):
            adapter = next(d for d in DETECTORS if self.scope in scope_keys(d))
            if len(self.candidates) > 32 or any(
                not isinstance(c, MetadataCandidate) or c.detail.adapter != adapter
                for c in self.candidates
            ):
                raise ValueError("unsupported_adapter_claim")
            indices = [c.detail.entry_index for c in self.candidates]
            if len(set(indices)) != len(indices):
                raise ValueError("duplicate_entry")
        elif any(not isinstance(c, Candidate) for c in self.candidates):
            raise ValueError("unsupported_product_claim")
        elif self.scope == "process-table-executable-v1":
            if any(c.basis == "bundle_metadata" or c.version is not None for c in self.candidates):
                raise ValueError("unsupported_process_claim")
        else:
            if len(self.candidates) > 1 or any(
                c.basis != "bundle_metadata" for c in self.candidates
            ):
                raise ValueError("unsupported_bundle_claim")
            key = (
                self.scope.removeprefix("macos-system-")
                .removeprefix("macos-user-")
                .removesuffix("-v1")
            )
            allowed = {key, "codex"} if key == "chatgpt" else {key}
            if any(c.product not in allowed for c in self.candidates):
                raise ValueError("product_outside_scope")
        allowed_reasons = {
            "complete": {"scoped_metadata_read", "process_table_read"},
            "missing": {"not_found"},
            "denied": {"permission_denied", "process_table_unavailable"},
            "unsupported": {
                "unsupported_platform",
                "dependency_unavailable",
                "project_not_selected",
                "manifest_not_selected",
            },
            "timeout": {"deadline_exceeded"},
            "malformed": {
                "invalid_worker_output",
                "worker_output_limit",
                "collector_failed",
                "invalid_metadata",
            },
            "partial": {
                "symlink_or_unsafe_file",
                "metadata_too_large",
                "metadata_changed",
                "invalid_metadata",
                "ambiguous_metadata",
                "deadline_exceeded",
                "entry_limit",
                "result_limit",
                "process_visibility_limited",
                "collector_failed",
                "entry_invalid",
                "precedence_unresolved",
            },
        }
        if self.reason not in allowed_reasons[self.status]:
            raise ValueError("contradictory_source_status")
        return self


def scope_keys(detector: Detector) -> tuple[str, ...]:
    from .catalog import APPLICATIONS

    if detector == "processes":
        return ("process-table-executable-v1",)
    if detector not in {"applications", "processes"}:
        return {
            "codex-mcp": ("codex-user-mcp-v1", "codex-project-mcp-v1"),
            "cursor-mcp": ("cursor-user-mcp-v1", "cursor-project-mcp-v1"),
            "ollama": ("ollama-manifests-v1",),
            "langgraph": ("langgraph-project-v1",),
            "agent-manifest": ("selected-agent-manifest-v1",),
        }[detector]
    return tuple(f"macos-{root}-{p.key}-v1" for root in ("system", "user") for p in APPLICATIONS)


class Finding(Contract):
    observation: Observation
    evidence: EvidenceState
    detail: MetadataDetail | None = None
    association: Association | None = None


class SourceScan(Contract):
    scope: str
    source_slot_id: Identifier
    detector: Detector
    status: Status
    reason: Reason
    findings: Entries[Finding]
    unknown_entries: Annotated[int, Field(ge=0, le=4096)] = 0


class ScanReport(Contract):
    schema_version: Literal["1.0"]
    scan_id: Identifier
    started_at: UTC
    finished_at: UTC
    elapsed_ms: Counter
    storage: Literal["not_saved"]
    continuity: Literal["not_evaluated"]
    scope: Literal["supported-products-only-v1", "selected-passive-metadata-v2"]
    sources: Entries[SourceScan]

    @property
    def candidate_count(self) -> int:
        return sum(
            sum(f.observation.manifest is not None for f in s.findings) for s in self.sources
        )
