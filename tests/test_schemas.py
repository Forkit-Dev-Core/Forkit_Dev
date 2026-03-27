"""Tests for ModelPassport and AgentPassport schemas."""

import pytest
from forkit.domain import verify_passport_id
from forkit_core.schemas import (
    AgentArchitecture,
    AgentPassport,
    AgentTaskType,
    Architecture,
    CreatorInfo,
    LicenseType,
    ModelPassport,
    PassportStatus,
    TaskType,
)

CREATOR = {"name": "Hamza", "organization": "ForkIt"}
FAKE_HASH = "a" * 64
FAKE_PARENT_HASH = "b" * 64


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def make_model(**kwargs) -> ModelPassport:
    defaults = dict(
        name="llama-3-8b-ft",
        version="1.0.0",
        task_type=TaskType.TEXT_GENERATION,
        architecture=Architecture.DECODER_ONLY,
        creator=CREATOR,
        license=LicenseType.APACHE_2,
    )
    defaults.update(kwargs)
    return ModelPassport(**defaults)


def make_agent(model_id: str, **kwargs) -> AgentPassport:
    defaults = dict(
        name="support-agent",
        version="1.0.0",
        model_id=model_id,
        task_type=AgentTaskType.CUSTOMER_SUPPORT,
        architecture=AgentArchitecture.REACT,
        creator=CREATOR,
        license=LicenseType.APACHE_2,
    )
    defaults.update(kwargs)
    return AgentPassport(**defaults)


# ──────────────────────────────────────────────────────────────────────────────
# ModelPassport
# ──────────────────────────────────────────────────────────────────────────────

class TestModelPassport:

    def test_required_fields_present(self):
        m = make_model()
        assert m.name == "llama-3-8b-ft"
        assert m.version == "1.0.0"
        assert m.task_type == TaskType.TEXT_GENERATION
        assert m.architecture == Architecture.DECODER_ONLY
        assert m.creator.name == "Hamza"
        assert m.license == LicenseType.APACHE_2
        assert m.passport_type == "model"

    def test_id_auto_assigned(self):
        m = make_model()
        assert m.id and len(m.id) == 64

    def test_id_deterministic_without_artifact_hash(self):
        m1 = make_model()
        m2 = make_model()
        assert m1.id == m2.id

    def test_id_deterministic_with_artifact_hash(self):
        m1 = make_model(artifact_hash=FAKE_HASH)
        m2 = make_model(artifact_hash=FAKE_HASH)
        assert m1.id == m2.id

    def test_artifact_hash_changes_id(self):
        m_no_hash   = make_model()
        m_with_hash = make_model(artifact_hash=FAKE_HASH)
        assert m_no_hash.id != m_with_hash.id

    def test_different_artifact_hashes_different_ids(self):
        m1 = make_model(artifact_hash=FAKE_HASH)
        m2 = make_model(artifact_hash="c" * 64)
        assert m1.id != m2.id

    def test_parent_hash_stored(self):
        m = make_model(parent_hash=FAKE_PARENT_HASH)
        assert m.parent_hash == FAKE_PARENT_HASH

    def test_model_id_optional(self):
        m = make_model()
        assert m.model_id is None

    def test_model_id_stored(self):
        m = make_model(model_id="meta-llama/Llama-3-8B-Instruct")
        assert m.model_id == "meta-llama/Llama-3-8B-Instruct"

    def test_version_changes_id(self):
        m1 = make_model(version="1.0.0")
        m2 = make_model(version="2.0.0")
        assert m1.id != m2.id

    def test_default_status_draft(self):
        m = make_model()
        assert m.status == PassportStatus.DRAFT

    def test_external_metadata_does_not_change_id(self):
        context_a = {
            "context": {
                "sync_state": "queued",
                "label": "alpha",
                "review_note": "first pass",
                "runtime_profile": "cpu",
                "integration_target": "local-registry",
            }
        }
        context_b = {
            "context": {
                "sync_state": "synced",
                "label": "beta",
                "review_note": "second pass",
                "runtime_profile": "gpu",
                "integration_target": "remote-bridge",
            }
        }

        m1 = make_model(metadata=context_a, status=PassportStatus.DRAFT)
        m2 = make_model(metadata=context_b, status=PassportStatus.ACTIVE)

        assert m1.id == m2.id
        assert verify_passport_id(m1.to_dict())["valid"] is True
        assert verify_passport_id(m2.to_dict())["valid"] is True

    def test_creator_org_is_identity_but_metadata_labels_are_not(self):
        m1 = make_model(
            creator={"name": "Hamza", "organization": "ForkIt"},
            metadata={"context": {"label": "owner-a"}},
        )
        m2 = make_model(
            creator={"name": "Hamza", "organization": "ForkIt"},
            metadata={"context": {"label": "owner-b"}},
        )
        m3 = make_model(
            creator={"name": "Hamza", "organization": "Another Org"},
            metadata={"context": {"label": "owner-a"}},
        )

        assert m1.id == m2.id
        assert m1.id != m3.id

    def test_to_dict_roundtrip(self):
        m = make_model(
            tags=["llm", "arabic"],
            artifact_hash=FAKE_HASH,
            parent_hash=FAKE_PARENT_HASH,
        )
        d = m.to_dict()
        m2 = ModelPassport(**d)
        assert m.id == m2.id
        assert m2.artifact_hash == FAKE_HASH
        assert m2.parent_hash == FAKE_PARENT_HASH

    def test_invalid_artifact_hash_rejected(self):
        with pytest.raises(Exception):
            make_model(artifact_hash="not-a-valid-hash")

    def test_invalid_version_rejected(self):
        with pytest.raises(Exception):
            make_model(version="invalid")

    def test_short_id(self):
        m = make_model()
        assert len(m.short_id()) == 12
        assert m.id.startswith(m.short_id())

    def test_all_task_types_accepted(self):
        for tt in TaskType:
            m = make_model(task_type=tt)
            assert m.task_type == tt

    def test_all_architectures_accepted(self):
        for arch in Architecture:
            m = make_model(architecture=arch)
            assert m.architecture == arch

    def test_all_licenses_accepted(self):
        for lic in LicenseType:
            m = make_model(license=lic)
            assert m.license == lic


# ──────────────────────────────────────────────────────────────────────────────
# AgentPassport
# ──────────────────────────────────────────────────────────────────────────────

class TestAgentPassport:

    def test_required_fields_present(self):
        m = make_model()
        a = make_agent(model_id=m.id)
        assert a.name == "support-agent"
        assert a.version == "1.0.0"
        assert a.model_id == m.id
        assert a.task_type == AgentTaskType.CUSTOMER_SUPPORT
        assert a.architecture == AgentArchitecture.REACT
        assert a.creator.name == "Hamza"
        assert a.license == LicenseType.APACHE_2
        assert a.passport_type == "agent"

    def test_id_auto_assigned(self):
        m = make_model()
        a = make_agent(model_id=m.id)
        assert a.id and len(a.id) == 64

    def test_id_deterministic(self):
        m = make_model()
        a1 = make_agent(model_id=m.id)
        a2 = make_agent(model_id=m.id)
        assert a1.id == a2.id

    def test_artifact_hash_changes_id(self):
        m = make_model()
        a_no_hash   = make_agent(model_id=m.id)
        a_with_hash = make_agent(model_id=m.id, artifact_hash=FAKE_HASH)
        assert a_no_hash.id != a_with_hash.id

    def test_parent_hash_stored(self):
        m = make_model()
        a = make_agent(model_id=m.id, parent_hash=FAKE_PARENT_HASH)
        assert a.parent_hash == FAKE_PARENT_HASH

    def test_tools_default_empty(self):
        m = make_model()
        a = make_agent(model_id=m.id)
        assert a.tools == []

    def test_agent_external_metadata_does_not_change_id(self):
        m = make_model()
        a1 = make_agent(
            model_id=m.id,
            metadata={"context": {"sync_state": "queued", "runtime_profile": "cpu"}},
            status=PassportStatus.DRAFT,
        )
        a2 = make_agent(
            model_id=m.id,
            metadata={"context": {"sync_state": "synced", "runtime_profile": "gpu"}},
            status=PassportStatus.ACTIVE,
        )

        assert a1.id == a2.id
        assert verify_passport_id(a1.to_dict())["valid"] is True
        assert verify_passport_id(a2.to_dict())["valid"] is True

    def test_to_dict_roundtrip(self):
        m = make_model()
        a = make_agent(model_id=m.id, artifact_hash=FAKE_HASH)
        d = a.to_dict()
        a2 = AgentPassport(**d)
        assert a.id == a2.id
        assert a2.model_id == m.id
        assert a2.artifact_hash == FAKE_HASH

    def test_all_agent_task_types_accepted(self):
        m = make_model()
        for tt in AgentTaskType:
            a = make_agent(model_id=m.id, task_type=tt)
            assert a.task_type == tt

    def test_all_agent_architectures_accepted(self):
        m = make_model()
        for arch in AgentArchitecture:
            a = make_agent(model_id=m.id, architecture=arch)
            assert a.architecture == arch

    def test_fork_fields(self):
        m = make_model()
        parent = make_agent(model_id=m.id, name="parent-agent")
        child = make_agent(
            model_id=m.id,
            name="child-agent",
            parent_hash=FAKE_PARENT_HASH,
            parent_agent_name="parent-agent",
            fork_reason="specialized for Arabic",
        )
        assert child.parent_hash == FAKE_PARENT_HASH
        assert child.parent_agent_name == "parent-agent"
        assert child.fork_reason == "specialized for Arabic"

    def test_model_and_agent_ids_differ(self):
        m = make_model(name="my-model")
        a = make_agent(model_id=m.id, name="my-model")
        # Same name, same version, same creator — but different passport_type
        assert m.id != a.id
