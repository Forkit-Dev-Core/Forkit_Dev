from __future__ import annotations

import copy
import hashlib
import json
from importlib.resources import files
from pathlib import Path

import pytest
from pydantic import ValidationError

from forkit_radar.contracts import CONTRACTS, Manifest, read_contract
from forkit_radar.jsonio import ContractError

FIXTURES = Path(__file__).parent / "fixtures"
ADVERSARIAL = json.loads((FIXTURES / "adversarial.json").read_text())


def fixture(name):
    return json.loads((FIXTURES / f"{name}.json").read_text())


def parse(name, value):
    return read_contract(name, json.dumps(value).encode())


@pytest.mark.parametrize("name", CONTRACTS)
def test_valid_contract_round_trip_is_immutable(name):
    value = fixture(name)
    parsed = parse(name, value)
    assert parsed.model_dump(mode="json", by_alias=True) == value
    assert parse(name, parsed.model_dump(mode="json", by_alias=True)) == parsed
    with pytest.raises(ValidationError):
        parsed.unrecognized_attribute = "forbidden"


@pytest.mark.parametrize("case", ADVERSARIAL, ids=lambda c: c["case_id"])
def test_adversarial_contract_corpus(case):
    document = fixture(case["contract"])
    for path, value in case["changes"].items():
        target = document
        fields = path.split(".")
        for name in fields[:-1]:
            target = target[name]
        target[fields[-1]] = value
    with pytest.raises(ContractError) as error:
        parse(case["contract"], document)
    assert str(error.value) in {"invalid_contract", "non_integer_number"}
    assert "SENTINEL" not in str(error.value)


@pytest.mark.parametrize("name", CONTRACTS)
def test_unknown_fields_do_not_survive_validation(name):
    document = fixture(name)
    document["SENTINEL-PRIVATE-FIELD"] = "SENTINEL-SECRET"
    with pytest.raises(ContractError, match="^invalid_contract$"):
        parse(name, document)


def test_input_mutation_cannot_change_a_validated_record():
    data = fixture("manifest")
    record = parse("manifest", data)
    data["scope_profile"]["dimensions"].clear()
    data["declared_identity"]["name"]["value"] = "mutated"
    assert record.declared_identity.name.value == "support-agent"
    assert record.scope_profile.dimensions == ("identity", "tools", "models", "settings")
    with pytest.raises(ValidationError):
        record.declared_identity.name.value = "mutated"


def test_known_empty_and_unavailable_remain_distinct():
    available = parse("manifest", fixture("manifest"))
    missing = fixture("manifest")
    missing["tools"] = None
    missing["measurement_completeness"]["tools"] = "unavailable"
    unavailable = parse("manifest", missing)
    assert available.tools == ()
    assert unavailable.tools is None
    assert available != unavailable


def test_partial_source_record_preserves_unknown_and_does_not_imply_removal():
    observation = parse("observation", fixture("observation"))
    assert observation.source_status == "partial"
    assert observation.manifest.models is None
    assert observation.manifest.measurement_completeness.models == "unavailable"
    denied = fixture("observation")
    denied.update(source_status="denied", manifest=None)
    assert parse("observation", denied).manifest is None


def test_distinct_enrollments_can_refer_to_same_passport_and_name():
    # Contract independence only; this is not a resolver/continuity integration test.
    first = fixture("manifest")
    first.update(
        logical_agent_id="00000002-1234-4123-8123-123456789abc",
        provisional_component_key=None,
        passport_id="a" * 64,
    )
    second = copy.deepcopy(first)
    second["logical_agent_id"] = "00000003-1234-4123-8123-123456789abc"
    a, b = parse("manifest", first), parse("manifest", second)
    assert a.passport_id == b.passport_id
    assert a.declared_identity.name == b.declared_identity.name
    assert a.logical_agent_id != b.logical_agent_id
    assert "acceptance" not in type(a).model_fields


def test_pending_proposal_carries_no_authorization_result():
    pending = parse("transition", fixture("transition"))
    assert pending.status == "pending"
    assert pending.authorization_evidence_ids == ()
    assert pending.logical_agent_id is None


def test_signature_shaped_data_is_not_authenticated():
    # The fixture has an all-zero signature; parsing must not invent a verified state.
    envelope = parse("dsse-envelope", fixture("dsse-envelope"))
    assert "verified" not in type(envelope).model_fields
    assert "authority" not in type(envelope).model_fields


def test_a_supported_runtime_claim_has_session_scope_and_bounded_expiry():
    data = fixture("evidence")
    data.update(
        axis="runtime",
        state="process_correlated",
        basis="os_peer",
        instance_id="00000005-1234-4123-8123-123456789abc",
        expires_at="2026-09-14T10:01:00Z",
        supporting_evidence_ids=["00000003-1234-4123-8123-123456789abc"],
    )
    assert parse("evidence", data).state == "process_correlated"
    for update in (
        {"instance_id": None},
        {"revision_digest": None},
        {"logical_agent_id": None},
        {"expires_at": "2026-09-14T10:01:01Z"},
        {"expires_at": "2026-09-14T10:00:00Z"},
        {"checked_at": None},
        {"supporting_evidence_ids": []},
    ):
        with pytest.raises(ContractError):
            parse("evidence", data | update)


@pytest.mark.parametrize("dimension", ["identity", "tools", "models", "artifacts", "settings"])
def test_scope_and_completeness_cannot_disagree(dimension):
    data = fixture("manifest")
    data["measurement_completeness"][dimension] = "complete"
    data["scope_profile"]["dimensions"] = [
        x for x in data["scope_profile"]["dimensions"] if x != dimension
    ]
    with pytest.raises(ContractError):
        parse("manifest", data)


def test_semantic_set_duplicates_are_rejected_without_reordering_sequences():
    data = fixture("manifest")
    data["scope_profile"]["dimensions"].append("tools")
    with pytest.raises(ContractError):
        parse("manifest", data)
    data = fixture("manifest")
    data["scope_profile"]["dimensions"].reverse()
    assert parse("manifest", data).scope_profile.dimensions == tuple(
        data["scope_profile"]["dimensions"]
    )
    # Actual semantic set normalization and revision digests belong to S06.


def test_self_supporting_evidence_is_rejected():
    data = fixture("evidence")
    data["supporting_evidence_ids"] = [data["evidence_id"]]
    with pytest.raises(ContractError):
        parse("evidence", data)


@pytest.mark.parametrize("name", CONTRACTS)
def test_distributed_schema_matches_python_shape(name):
    stored = files("forkit_radar").joinpath("schemas", f"{name}-v1.json").read_text()
    assert json.loads(stored) == CONTRACTS[name].model_json_schema(by_alias=True)


def test_core_identity_and_regression_sources_remain_unchanged():
    from forkit.domain.identity import compute_id

    reference = fixture("core-reference")
    assert compute_id(**reference["identity_input"]) == reference["expected_passport_id"]
    repository = Path(__file__).resolve().parents[3]
    if not (repository / "forkit").is_dir():
        pytest.skip("Source hash check is repository-only; wheel identity check still ran")
    for name, expected in reference["sha256"].items():
        assert hashlib.sha256((repository / name).read_bytes()).hexdigest() == expected, name


def test_raw_core_missing_id_fixture_is_rejected_before_schema_repair():
    from forkit.domain.integrity import verify_passport_id

    reference = fixture("core-reference")
    raw = {
        "passport_type": "agent",
        "name": "support-agent",
        "version": "1.0.0",
        "creator": {"name": "Example developer", "organization": None},
        "artifact_hash": None,
    }
    assert verify_passport_id(raw)["reason"] == "missing_id"
    raw["id"] = reference["expected_passport_id"]
    assert verify_passport_id(raw)["valid"] is True
    raw["id"] = "0" * 64
    assert verify_passport_id(raw)["reason"] == "id_mismatch"


def test_boolean_is_not_an_authority_scope_integer_or_string():
    data = fixture("runtime-challenge")
    data["peer"]["uid"] = False
    with pytest.raises(ContractError):
        parse("runtime-challenge", data)
    data = fixture("authority")
    data["scope"]["allow_new_enrollment"] = 1
    with pytest.raises(ContractError):
        parse("authority", data)


def test_manifest_has_no_automatic_creation_defaults():
    with pytest.raises(ValidationError):
        Manifest()


@pytest.mark.parametrize(
    "timestamp",
    [
        "٢٠٢٦-09-14T10:00:00Z",
        "2026-02-30T10:00:00Z",
        "2026-09-14T10:00:00+00:00",
        "2026-09-14T10:00:00Z\n",
    ],
)
def test_timestamp_spelling_is_valid_ascii_utc(timestamp):
    data = fixture("observation")
    data["observed_at"] = timestamp
    with pytest.raises(ContractError):
        parse("observation", data)


def test_nonempty_metadata_collections_remain_typed_and_private():
    data = fixture("manifest")
    observed = {"value": "fixture", "origin": "supported_metadata"}
    data["tools"] = [
        {
            "key": "search",
            "name": observed,
            "origin": "supported_metadata",
            "transport": "in_process",
            "permissions": ["read_metadata"],
        }
    ]
    data["models"] = [
        {
            "key": "model",
            "origin": "supported_metadata",
            "name": observed,
            "version": observed,
            "provider": observed,
            "passport_id": "a" * 64,
            "digest": {"value": None, "origin": "unknown"},
        }
    ]
    data["measurement_completeness"]["models"] = "complete"
    data["scope_profile"]["dimensions"].append("artifacts")
    data["artifacts"] = [
        {
            "key": "config",
            "kind": "config_bundle",
            "digest": {"value": "b" * 64, "origin": "declared"},
            "hashing_profile": "manifest-sha256-v1",
        }
    ]
    data["measurement_completeness"]["artifacts"] = "complete"
    assert parse("manifest", data).tools[0].permissions == ("read_metadata",)
    for dimension in ("tools", "models", "artifacts"):
        duplicate = copy.deepcopy(data)
        duplicate[dimension].append(copy.deepcopy(duplicate[dimension][0]))
        with pytest.raises(ContractError):
            parse("manifest", duplicate)
    data["models"][0]["endpoint"] = "https://SENTINEL-PRIVATE.invalid"
    with pytest.raises(ContractError, match="^invalid_contract$"):
        parse("manifest", data)


@pytest.mark.parametrize(
    "operation",
    [
        "observe",
        "accept_revision",
        "move",
        "fork",
        "migrate",
        "retire",
        "rotate_key",
        "revoke_key",
        "recover",
    ],
)
def test_lifecycle_operations_have_pending_proposal_shapes(operation):
    data = fixture("transition")
    data.update(operation=operation, logical_agent_id="00000002-1234-4123-8123-123456789abc")
    if operation == "observe":
        data["intent"] = "automatic_observation"
    if operation in {"move", "migrate"}:
        data["target_source_slot_id"] = "00000005-1234-4123-8123-123456789abc"
    if operation == "fork":
        data["target_logical_agent_id"] = "00000005-1234-4123-8123-123456789abc"
    if operation in {"rotate_key", "recover"}:
        data["new_authority_id"] = "00000005-1234-4123-8123-123456789abc"
    assert parse("transition", data).status == "pending"
