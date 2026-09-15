"""Versioned, immutable wire contracts. Schema validity is never authentication.

No validator resolves a source, loads a key, signs, enrolls or accepts a
revision. Trust decisions require the future verifier and protected store.
"""

from __future__ import annotations

import base64
import binascii
import unicodedata
from datetime import datetime
from decimal import Decimal
from typing import Annotated, Literal, TypeVar

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)

from .jsonio import MAX_SAFE_INTEGER, ContractError, load_json

T = TypeVar("T")


def _array(value: object) -> tuple:
    if type(value) not in (list, tuple):
        raise ValueError("array_required")
    return tuple(value)


def _display_text(value: str) -> str:
    if any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value):
        raise ValueError("control_character")
    return value


def _utc(value: str) -> str:
    try:
        datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        raise ValueError("invalid_utc_time") from None
    return value


def _base64(value: str, size: int) -> str:
    try:
        raw = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        raise ValueError("invalid_base64") from None
    if len(raw) != size or base64.b64encode(raw).decode("ascii") != value:
        raise ValueError("invalid_base64_size_or_encoding")
    return value


def _unique(values: tuple) -> None:
    if len(values) != len(set(values)):
        raise ValueError("duplicate_member")


def _unique_keys(values: tuple | None) -> None:
    if values is not None:
        _unique(tuple(v.key for v in values))


Entries = Annotated[tuple[T, ...], BeforeValidator(_array), Field(max_length=256)]
Identifier = Annotated[
    str, Field(pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
Token = Annotated[str, Field(min_length=1, max_length=80, pattern=r"^[a-z0-9][a-z0-9_.-]*$")]
Text = Annotated[str, Field(min_length=1, max_length=256), AfterValidator(_display_text)]
UTC = Annotated[
    str,
    Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}Z$"),
    AfterValidator(_utc),
]
Counter = Annotated[int, Field(ge=0, le=MAX_SAFE_INTEGER)]
Sequence = Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)]
DecimalSetting = Annotated[str, Field(pattern=r"^(0|[1-9][0-9]{0,2})(\.[0-9]{1,8})?$")]
PublicKey = Annotated[
    str, Field(min_length=44, max_length=44), AfterValidator(lambda v: _base64(v, 32))
]
Signature = Annotated[
    str, Field(min_length=88, max_length=88), AfterValidator(lambda v: _base64(v, 64))
]
Origin = Literal["unknown", "declared", "supported_metadata", "independently_measured"]
Dimension = Literal["identity", "tools", "models", "artifacts", "settings"]
Completeness = Literal["complete", "partial", "unavailable", "unsupported", "not_selected"]
Operation = Literal[
    "enroll",
    "observe",
    "accept_revision",
    "move",
    "fork",
    "migrate",
    "retire",
    "rotate_key",
    "revoke_key",
    "recover",
]


class Contract(BaseModel):
    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        validate_default=True,
        revalidate_instances="always",
    )


class ObservedText(Contract):
    value: Text | None
    origin: Origin

    @model_validator(mode="after")
    def unknown_has_no_value(self):
        if self.origin == "unknown" and self.value is not None:
            raise ValueError("unknown_value_must_be_null")
        return self


class ObservedDigest(Contract):
    value: Digest | None
    origin: Origin

    @model_validator(mode="after")
    def unknown_has_no_value(self):
        if self.origin == "unknown" and self.value is not None:
            raise ValueError("unknown_value_must_be_null")
        return self


class DeclaredIdentity(Contract):
    name: ObservedText
    version: ObservedText
    creator: ObservedText
    organization: ObservedText


class ScopeProfile(Contract):
    profile_id: Literal["passive-metadata-v1", "consented-artifacts-v1", "runtime-adapter-v1"]
    normalization_version: Literal["1"]
    dimensions: Entries[Dimension]

    @model_validator(mode="after")
    def unique_dimensions(self):
        _unique(self.dimensions)
        if not self.dimensions:
            raise ValueError("scope_required")
        return self


class ToolMetadata(Contract):
    key: Token
    name: ObservedText
    origin: Origin
    transport: Literal["stdio", "http", "in_process", "unknown"]
    permissions: (
        Entries[Literal["read_metadata", "read_files", "write_files", "network", "execute"]] | None
    )

    @model_validator(mode="after")
    def unique_permissions(self):
        if self.permissions is not None:
            _unique(self.permissions)
        return self


class ModelReference(Contract):
    key: Token
    origin: Origin
    name: ObservedText
    version: ObservedText
    provider: ObservedText
    passport_id: Digest | None
    digest: ObservedDigest


class ArtifactMetadata(Contract):
    key: Token
    kind: Literal["file", "tree", "config_bundle", "model_metadata"]
    digest: ObservedDigest
    hashing_profile: Literal[
        "core-file-sha256-v1", "core-directory-sha256-v1", "manifest-sha256-v1", "unknown"
    ]

    @model_validator(mode="after")
    def measurement_needs_profile(self):
        if self.digest.origin == "independently_measured" and (
            self.digest.value is None or self.hashing_profile == "unknown"
        ):
            raise ValueError("measurement_profile_required")
        return self


class Settings(Contract):
    origin: Origin
    temperature: DecimalSetting | None
    top_p: DecimalSetting | None
    max_tokens: Annotated[int, Field(ge=1, le=MAX_SAFE_INTEGER)] | None

    @model_validator(mode="after")
    def check_values(self):
        if self.top_p is not None and Decimal(self.top_p) > 1:
            raise ValueError("top_p_out_of_range")
        if self.origin == "unknown" and any(
            v is not None for v in (self.temperature, self.top_p, self.max_tokens)
        ):
            raise ValueError("unknown_value_must_be_null")
        return self


class MeasurementCompleteness(Contract):
    identity: Completeness
    tools: Completeness
    models: Completeness
    artifacts: Completeness
    settings: Completeness


class Manifest(Contract):
    schema_version: Literal["1.0"]
    logical_agent_id: Identifier | None
    provisional_component_key: Identifier | None
    passport_id: Digest | None
    component_kind: Literal["agent", "model", "application", "runtime", "tool", "mcp_server"]
    scope_profile: ScopeProfile
    declared_identity: DeclaredIdentity
    tools: Entries[ToolMetadata] | None
    models: Entries[ModelReference] | None
    artifacts: Entries[ArtifactMetadata] | None
    settings: Settings | None
    measurement_completeness: MeasurementCompleteness

    @model_validator(mode="after")
    def check_scope(self):
        if (self.logical_agent_id is None) == (self.provisional_component_key is None):
            raise ValueError("exactly_one_local_identifier_required")
        for dimension in ("tools", "models", "artifacts", "settings"):
            value = getattr(self, dimension)
            status = getattr(self.measurement_completeness, dimension)
            if (dimension not in self.scope_profile.dimensions) != (status == "not_selected"):
                raise ValueError("dimension_outside_scope")
            if status == "complete" and value is None:
                raise ValueError("complete_dimension_requires_value")
            if status in {"not_selected", "unsupported", "unavailable"} and value is not None:
                raise ValueError("unavailable_dimension_must_be_null")
        for values in (self.tools, self.models, self.artifacts):
            _unique_keys(values)
        identity_status = self.measurement_completeness.identity
        if ("identity" not in self.scope_profile.dimensions) != (identity_status == "not_selected"):
            raise ValueError("identity_outside_scope")
        identity_fields = (
            self.declared_identity.name,
            self.declared_identity.version,
            self.declared_identity.creator,
            self.declared_identity.organization,
        )
        if identity_status == "complete" and any(v.origin == "unknown" for v in identity_fields):
            raise ValueError("unknown_identity_is_not_complete")
        if identity_status in {"not_selected", "unsupported", "unavailable"} and any(
            v.origin != "unknown" for v in identity_fields
        ):
            raise ValueError("unavailable_identity_must_be_unknown")
        return self


class Observation(Contract):
    schema_version: Literal["1.0"]
    observation_id: Identifier
    source_slot_id: Identifier
    observed_at: UTC
    detector_id: Token
    detector_version: Token
    source_status: Literal[
        "complete", "partial", "denied", "missing", "unsupported", "timeout", "malformed"
    ]
    reason_code: Token
    manifest: Manifest | None

    @model_validator(mode="after")
    def failed_read_is_not_inventory(self):
        if self.source_status not in {"complete", "partial"} and self.manifest is not None:
            raise ValueError("failed_source_has_no_new_manifest")
        return self


class EvidenceState(Contract):
    discovery: Literal["configured", "observed", "unknown", "unavailable"]
    association: Literal["unmatched", "declared", "enrolled", "ambiguous", "conflicted"]
    passport: Literal["absent", "consistent", "invalid", "unsupported"]
    artifact: Literal["not_measured", "declared_digest", "matched", "mismatch", "partial"]
    provenance: Literal["absent", "untrusted_signer", "verified", "invalid", "stale"]
    runtime: Literal["not_observed", "process_correlated", "externally_authenticated", "expired"]
    acceptance: Literal["unreviewed", "accepted", "superseded", "revoked"]
    freshness: Literal["current_at_check", "stale", "unknown"]


Axis = Literal[
    "discovery",
    "association",
    "passport",
    "artifact",
    "provenance",
    "runtime",
    "acceptance",
    "freshness",
]
AXIS_STATES = {
    name: frozenset(field.annotation.__args__) for name, field in EvidenceState.model_fields.items()
}


class EvidenceRecord(Contract):
    schema_version: Literal["1.0"]
    evidence_id: Identifier
    axis: Axis
    state: Token
    basis: Literal[
        "none",
        "declared",
        "supported_metadata",
        "independently_measured",
        "os_peer",
        "local_authority",
        "external_verifier",
        "adapter_report",
        "core_identity_check",
    ]
    logical_agent_id: Identifier | None
    passport_id: Digest | None
    revision_digest: Digest | None
    instance_id: Identifier | None
    authority_id: Identifier | None
    scope_profile: Token
    reason_code: Token
    checked_at: UTC | None
    expires_at: UTC | None
    supporting_evidence_ids: Entries[Identifier]
    verifier_version: Token
    policy_version: Token

    @model_validator(mode="after")
    def check_claim_shape(self):
        if self.state not in AXIS_STATES[self.axis]:
            raise ValueError("invalid_axis_state")
        _unique(self.supporting_evidence_ids)
        if self.evidence_id in self.supporting_evidence_ids:
            raise ValueError("self_supporting_evidence")
        if self.expires_at is not None and (
            self.checked_at is None or self.expires_at <= self.checked_at
        ):
            raise ValueError("invalid_evidence_interval")
        strong = (self.axis, self.state)
        if strong == ("artifact", "matched") and self.basis != "independently_measured":
            raise ValueError("independent_measurement_required")
        if strong == ("provenance", "verified") and self.basis != "external_verifier":
            raise ValueError("external_verifier_required")
        if strong in {("association", "enrolled"), ("acceptance", "accepted")} and (
            self.basis != "local_authority"
            or self.authority_id is None
            or self.logical_agent_id is None
        ):
            raise ValueError("scoped_authority_required")
        if strong == ("passport", "consistent") and (
            self.basis != "core_identity_check"
            or self.passport_id is None
            or self.checked_at is None
            or not self.supporting_evidence_ids
        ):
            raise ValueError("raw_identity_check_required")
        if strong in {
            ("artifact", "matched"),
            ("provenance", "verified"),
            ("acceptance", "accepted"),
            ("association", "enrolled"),
        }:
            if (
                self.revision_digest is None
                or self.checked_at is None
                or not self.supporting_evidence_ids
            ):
                raise ValueError("scoped_support_required")
        if self.axis == "runtime" and self.state in {
            "process_correlated",
            "externally_authenticated",
        }:
            expected = "os_peer" if self.state == "process_correlated" else "external_verifier"
            if (
                self.basis != expected
                or any(
                    v is None
                    for v in (
                        self.logical_agent_id,
                        self.revision_digest,
                        self.instance_id,
                        self.checked_at,
                        self.expires_at,
                    )
                )
                or not self.supporting_evidence_ids
            ):
                raise ValueError("runtime_scope_required")
            interval = datetime.strptime(self.expires_at, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(
                self.checked_at, "%Y-%m-%dT%H:%M:%SZ"
            )
            if interval.total_seconds() > 60:
                raise ValueError("runtime_window_too_long")
        return self


class AuthorityScope(Contract):
    logical_agent_ids: Entries[Identifier]
    allow_new_enrollment: bool

    @model_validator(mode="after")
    def unique_agents(self):
        _unique(self.logical_agent_ids)
        return self


class AuthorityRecord(Contract):
    schema_version: Literal["1.0"]
    authority_id: Identifier
    algorithm: Literal["ed25519"]
    public_key: PublicKey | None
    protection: Literal["os_credential_store", "explicit_file", "external", "unavailable"]
    role: Literal["operator", "recovery"]
    status: Literal["active", "revoked", "unavailable"]
    scope: AuthorityScope
    created_at: UTC
    revoked_at: UTC | None

    @model_validator(mode="after")
    def check_status(self):
        if self.status == "active" and (
            self.public_key is None or self.protection == "unavailable"
        ):
            raise ValueError("authority_key_unavailable")
        if (self.status == "revoked") != (self.revoked_at is not None):
            raise ValueError("revocation_time_required")
        if self.revoked_at is not None and self.revoked_at < self.created_at:
            raise ValueError("invalid_revocation_time")
        return self


class TrustPolicy(Contract):
    schema_version: Literal["1.0"]
    policy_version: Literal["local-authority-scoped-v1"]
    automatic_enrollment: Literal["forbidden"]
    similarity_based_continuity: Literal["forbidden"]
    manifest_key_as_authority: Literal["forbidden"]
    copied_passport_as_ownership: Literal["forbidden"]
    revision_acceptance: Literal["explicit_scoped_authority"]
    rotation: Literal["old_authority_and_new_key_possession"]
    lost_key_recovery: Literal["preestablished_recovery_or_continuity_gap"]
    default_network: Literal["forbidden"]
    default_execution: Literal["forbidden"]
    signed_self_report: Literal["not_independent_authenticity"]


class SourceBinding(Contract):
    schema_version: Literal["1.0"]
    source_slot_id: Identifier
    logical_agent_id: Identifier
    authority_id: Identifier
    locator_token: Digest
    locator_scheme: Literal["hmac-sha256-local-v1"]
    accepted_binding_digest: Digest


class ObservedPeer(Contract):
    origin: Literal["collector_os"]
    pid: Annotated[int, Field(ge=1, le=2**31 - 1)]
    uid: Counter
    process_start_identity: Text


class RuntimeChallenge(Contract):
    schema_version: Literal["1.0"]
    challenge_id: Identifier
    nonce: PublicKey  # 32-byte random nonce; this shape does not generate or consume it.
    audience: Token
    logical_agent_id: Identifier
    revision_digest: Digest
    instance_id: Identifier
    source_slot_id: Identifier
    peer: ObservedPeer
    issued_at: UTC
    expires_at: UTC

    @model_validator(mode="after")
    def bounded_interval(self):
        delta = datetime.strptime(self.expires_at, "%Y-%m-%dT%H:%M:%SZ") - datetime.strptime(
            self.issued_at, "%Y-%m-%dT%H:%M:%SZ"
        )
        if not 0 < delta.total_seconds() <= 60:
            raise ValueError("invalid_challenge_window")
        return self


class TransitionProposal(Contract):
    schema_version: Literal["1.0"]
    proposal_id: Identifier
    status: Literal["pending"]
    operation: Operation
    intent: Literal["explicit", "automatic_observation"]
    logical_agent_id: Identifier | None
    target_logical_agent_id: Identifier | None
    candidate_passport_id: Digest | None
    candidate_revision_digest: Digest | None
    previous_event_digest: Digest | None
    previous_accepted_binding_digest: Digest | None
    requested_authority_id: Identifier | None
    new_authority_id: Identifier | None
    source_slot_id: Identifier | None
    target_source_slot_id: Identifier | None
    authorization_evidence_ids: Entries[Identifier]

    @model_validator(mode="after")
    def check_proposal(self):
        _unique(self.authorization_evidence_ids)
        if self.operation != "observe" and self.intent != "explicit":
            raise ValueError("explicit_intent_required")
        if self.operation != "enroll" and self.logical_agent_id is None:
            raise ValueError("existing_agent_required")
        if self.operation == "enroll" and any(
            v is not None
            for v in (
                self.logical_agent_id,
                self.previous_event_digest,
                self.previous_accepted_binding_digest,
            )
        ):
            raise ValueError("enrollment_cannot_join_existing_history")
        if (
            self.operation in {"enroll", "accept_revision", "fork"}
            and self.candidate_revision_digest is None
        ):
            raise ValueError("candidate_revision_required")
        if self.operation == "fork":
            if (
                self.target_logical_agent_id is None
                or self.target_logical_agent_id == self.logical_agent_id
            ):
                raise ValueError("fork_requires_distinct_agent")
        elif self.target_logical_agent_id is not None:
            raise ValueError("unexpected_target_agent")
        if self.operation in {"move", "migrate"} and (
            self.source_slot_id is None
            or self.target_source_slot_id is None
            or self.source_slot_id == self.target_source_slot_id
        ):
            raise ValueError("distinct_source_slots_required")
        if self.operation in {"rotate_key", "recover"}:
            if (
                self.new_authority_id is None
                or self.new_authority_id == self.requested_authority_id
            ):
                raise ValueError("new_authority_required")
        elif self.new_authority_id is not None:
            raise ValueError("unexpected_new_authority")
        return self


class BindingPredicate(Contract):
    schema_version: Literal["1.0"]
    logical_agent_id: Identifier
    passport_id: Digest | None
    revision_digest: Digest
    previous_event_digest: Digest | None
    previous_accepted_binding_digest: Digest | None
    event_type: Operation
    sequence: Sequence
    evidence_references: Entries[Identifier]
    verifier_version: Token
    policy_version: Token
    signer_scope: AuthorityScope
    verified_at: UTC

    @model_validator(mode="after")
    def check_links(self):
        _unique(self.evidence_references)
        if (self.sequence == 1) != (self.previous_event_digest is None):
            raise ValueError("previous_event_required_after_genesis")
        if self.sequence == 1 and self.previous_accepted_binding_digest is not None:
            raise ValueError("genesis_has_no_accepted_predecessor")
        if self.logical_agent_id not in self.signer_scope.logical_agent_ids:
            raise ValueError("signer_scope_missing_agent")
        return self


class SubjectDigest(Contract):
    sha256: Digest


class Subject(Contract):
    name: Identifier
    digest: SubjectDigest


class BindingStatement(Contract):
    statement_type: Literal["https://in-toto.io/Statement/v1"] = Field(alias="_type")
    subject: Annotated[Entries[Subject], Field(min_length=1, max_length=1)]
    predicate_type: Literal["https://forkit.dev/attestations/radar-binding/v1"] = Field(
        alias="predicateType"
    )
    predicate: BindingPredicate


class EnvelopeSignature(Contract):
    keyid: Token
    sig: Signature


class DSSEEnvelope(Contract):
    payload_type: Literal["application/vnd.in-toto+json"] = Field(alias="payloadType")
    payload: Annotated[str, Field(min_length=4, max_length=131_072)]
    signatures: Annotated[Entries[EnvelopeSignature], Field(min_length=1, max_length=4)]

    @model_validator(mode="after")
    def canonical_payload_encoding(self):
        try:
            raw = base64.b64decode(self.payload, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("invalid_base64") from None
        if base64.b64encode(raw).decode("ascii") != self.payload:
            raise ValueError("noncanonical_base64")
        _unique(tuple(s.keyid for s in self.signatures))
        return self


class PublicCounts(Contract):
    eligible_agents: Annotated[int, Field(ge=0, le=100_000)]
    eligible_models: Annotated[int, Field(ge=0, le=100_000)]
    consistent_passports: Annotated[int, Field(ge=0, le=200_000)]
    enrolled_agents: Annotated[int, Field(ge=0, le=100_000)]
    excluded_components: Annotated[int, Field(ge=0, le=200_000)]
    unknown_components: Annotated[int, Field(ge=0, le=200_000)]

    @model_validator(mode="after")
    def check_denominators(self):
        if self.consistent_passports > self.eligible_agents + self.eligible_models:
            raise ValueError("coverage_exceeds_denominator")
        if self.enrolled_agents > self.eligible_agents:
            raise ValueError("enrollment_exceeds_agents")
        return self


class PublicSnapshot(Contract):
    schema_version: Literal["1.0"]
    public_surface_id: Identifier
    publication_id: Identifier
    measurement_kind: Literal["self_reported"]
    counts: PublicCounts


CONTRACTS: dict[str, type[Contract]] = {
    "manifest": Manifest,
    "observation": Observation,
    "evidence-state": EvidenceState,
    "evidence": EvidenceRecord,
    "authority": AuthorityRecord,
    "trust-policy": TrustPolicy,
    "source-binding": SourceBinding,
    "runtime-challenge": RuntimeChallenge,
    "transition": TransitionProposal,
    "binding-predicate": BindingPredicate,
    "binding-statement": BindingStatement,
    "dsse-envelope": DSSEEnvelope,
    "public-snapshot": PublicSnapshot,
}


def read_contract(name: str, raw: bytes) -> Contract:
    """Validate untrusted bytes without ever asserting authority or authenticity."""
    contract = CONTRACTS.get(name)
    if contract is None:
        raise ContractError("unsupported_contract")
    value = load_json(raw)
    try:
        return contract.model_validate(value)
    except ValidationError:
        raise ContractError("invalid_contract") from None
