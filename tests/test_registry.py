"""Tests for the LocalRegistry."""

import pytest
from forkit_core.registry import LocalRegistry
from forkit_core.schemas import (
    AgentArchitecture,
    AgentPassport,
    AgentTaskType,
    ModelPassport,
    TaskType,
)


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


@pytest.fixture
def registry(tmp_path):
    reg = LocalRegistry(root=tmp_path / "registry")
    reg.init()
    return reg


def make_model(**kwargs) -> ModelPassport:
    defaults = dict(
        name="base-llm",
        version="1.0.0",
        task_type=TaskType.TEXT_GENERATION,
        architecture="transformer",
        creator=CREATOR,
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
    )
    defaults.update(kwargs)
    return AgentPassport(**defaults)


class TestLocalRegistry:
    def test_register_and_get_model(self, registry):
        m = make_model()
        pid = registry.register_model(m)
        assert pid == m.id
        fetched = registry.get_model(pid)
        assert fetched is not None
        assert fetched.name == m.name

    def test_register_and_get_agent(self, registry):
        m = make_model()
        registry.register_model(m)
        a = make_agent(model_id=m.id)
        pid = registry.register_agent(a)
        fetched = registry.get_agent(pid)
        assert fetched is not None
        assert fetched.model_id == m.id

    def test_get_unknown_returns_none(self, registry):
        assert registry.get_model("nonexistent") is None
        assert registry.get_agent("nonexistent") is None

    def test_generic_get(self, registry):
        m = make_model()
        pid = registry.register_model(m)
        result = registry.get(pid)
        assert result is not None
        assert result.id == pid

    def test_list_all(self, registry):
        m = make_model()
        registry.register_model(m)
        a = make_agent(model_id=m.id)
        registry.register_agent(a)
        results = registry.list()
        assert len(results) == 2

    def test_list_by_type(self, registry):
        m = make_model()
        registry.register_model(m)
        a = make_agent(model_id=m.id)
        registry.register_agent(a)
        models = registry.list(passport_type="model")
        agents = registry.list(passport_type="agent")
        assert len(models) == 1
        assert len(agents) == 1

    def test_search(self, registry):
        registry.register_model(make_model(name="llama-7b"))
        registry.register_model(make_model(name="mistral-7b", version="2.0.0"))
        results = registry.search("llama")
        assert len(results) == 1
        assert results[0]["name"] == "llama-7b"

    def test_delete(self, registry):
        m = make_model()
        pid = registry.register_model(m)
        assert registry.delete(pid) is True
        assert registry.get_model(pid) is None
        assert registry.delete(pid) is False

    def test_stats(self, registry):
        m = make_model()
        registry.register_model(m)
        s = registry.stats()
        assert s["models"] == 1
        assert s["agents"] == 0
        assert s["total"] == 1

    def test_verify_passport(self, registry):
        m = make_model()
        pid = registry.register_model(m)
        result = registry.verify_passport(pid)
        assert result["valid"] is True

    def test_lineage_populated_on_register(self, registry):
        m = make_model()
        registry.register_model(m)
        a = make_agent(model_id=m.id)
        registry.register_agent(a)
        lineage = registry.lineage
        assert lineage.get_node(m.id) is not None
        assert lineage.get_node(a.id) is not None

    def test_rebuild_index(self, registry):
        registry.register_model(make_model())
        registry.register_model(make_model(name="second-model", version="2.0.0"))
        count = registry.rebuild_index()
        assert count == 2

    def test_export_changes_returns_cursor_ordered_documents(self, registry):
        model = make_model()
        registry.register_model(model)
        agent = make_agent(model_id=model.id)
        registry.register_agent(agent)

        result = registry.export_changes()

        assert result["cursor"] == 2
        assert result["has_more"] is False
        assert [item["passport_id"] for item in result["items"]] == [model.id, agent.id]
        assert result["items"][0]["document"]["id"] == model.id
        assert result["items"][1]["document"]["id"] == agent.id

    def test_export_changes_includes_delete_tombstones(self, registry):
        model = make_model()
        registry.register_model(model)

        assert registry.delete(model.id) is True

        result = registry.export_changes()

        assert [item["operation"] for item in result["items"]] == ["upsert", "delete"]
        assert result["items"][0]["document"]["id"] == model.id
        assert result["items"][1]["passport_id"] == model.id
        assert result["items"][1]["document"] is None

    def test_apply_changes_imports_passports_without_reemitting_outbox(self, tmp_path):
        source = LocalRegistry(root=tmp_path / "source")
        source.init()
        model = make_model()
        source.register_model(model)
        agent = make_agent(model_id=model.id)
        source.register_agent(agent)

        target = LocalRegistry(root=tmp_path / "target")
        target.init()

        applied = target.apply_changes(source.export_changes()["items"])
        exported = target.export_changes()

        assert applied == {"applied": 2, "upserts": 2, "deletes": 0}
        assert target.get_model(model.id) is not None
        assert target.get_agent(agent.id) is not None
        assert exported["cursor"] == 0
        assert exported["items"] == []
