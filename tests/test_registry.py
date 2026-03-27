"""Tests for the LocalRegistry."""

import pytest
from forkit_core.registry import LocalRegistry
from forkit_core.schemas import AgentPassport, ModelPassport


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
        architecture="transformer",
        task_type="text-generation",
        creator=CREATOR,
    )
    defaults.update(kwargs)
    return ModelPassport(**defaults)


def make_agent(model_id: str, **kwargs) -> AgentPassport:
    defaults = dict(
        name="support-agent",
        version="1.0.0",
        model_id=model_id,
        task_type="customer-support",
        architecture="ReAct",
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
