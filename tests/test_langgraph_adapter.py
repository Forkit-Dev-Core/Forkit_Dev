"""Tests for the LangGraph adapter."""

from typing import TypedDict

import pytest
from forkit.sdk import ForkitClient
from forkit.schemas import AgentTaskType, TaskType
from forkit_langgraph import BoundLangGraphRunnable, LangGraphAdapter


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


class FakeState:
    pass


class FakeInput:
    pass


class FakeOutput:
    pass


class FakeContext:
    pass


class FakeBuilder:
    def __init__(self) -> None:
        self.name = "triage-builder"
        self.nodes = {"router": object(), "writer": object()}
        self.edges = {("START", "router"), ("router", "writer")}
        self.waiting_edges = {(("writer",), "END")}
        self.state_schema = FakeState
        self.input_schema = FakeInput
        self.output_schema = FakeOutput
        self.context_schema = FakeContext
        self.compile_calls: list[dict[str, object]] = []

    def compile(self, **kwargs):
        self.compile_calls.append(kwargs)
        return FakeCompiledGraph(self, kwargs)


class FakeCompiledGraph:
    def __init__(self, builder: FakeBuilder, compile_kwargs: dict[str, object]) -> None:
        self.builder = builder
        self.compile_kwargs = compile_kwargs
        self.invoke_calls: list[dict[str, object]] = []

    def get_name(self) -> str:
        return "compiled-triage-graph"

    def invoke(self, payload):
        self.invoke_calls.append(payload)
        return {"ok": True, "payload": payload}


class TestLangGraphAdapter:
    def test_register_agent_uses_graph_hash_as_artifact_hash(self, tmp_path):
        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangGraphAdapter(client=client)

        model_id = client.models.register(
            name="demo-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )
        graph_spec = {
            "entrypoint": "router",
            "nodes": ["router", "writer"],
            "edges": [["router", "writer"]],
        }

        agent_id = adapter.register_agent(
            name="writer-graph",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            task_type=AgentTaskType.OTHER,
            system_prompt="Draft the response before sending it.",
            graph_spec=graph_spec,
        )

        agent = client.agents.get(agent_id)
        graph_hash = adapter.hash_graph(graph_spec)

        assert agent is not None
        assert agent.artifact_hash == graph_hash
        assert agent.metadata["langgraph"]["graph_hash"] == graph_hash
        assert client.verify(agent_id)["valid"] is True

    def test_graph_spec_changes_agent_id(self, tmp_path):
        adapter = LangGraphAdapter(registry_root=tmp_path / "registry")

        graph_a = {"nodes": ["router", "search"], "edges": [["router", "search"]]}
        graph_b = {"nodes": ["router", "summarize"], "edges": [["router", "summarize"]]}

        passport_a = adapter.build_agent_passport(
            name="search-graph",
            version="1.0.0",
            model_id="m" * 64,
            creator=CREATOR,
            graph_spec=graph_a,
        )
        passport_b = adapter.build_agent_passport(
            name="search-graph",
            version="1.0.0",
            model_id="m" * 64,
            creator=CREATOR,
            graph_spec=graph_b,
        )

        assert passport_a.artifact_hash != passport_b.artifact_hash
        assert passport_a.id != passport_b.id

    def test_extract_graph_spec_from_builder(self, tmp_path):
        adapter = LangGraphAdapter(registry_root=tmp_path / "registry")
        builder = FakeBuilder()

        spec = adapter.extract_graph_spec(builder)

        assert spec["compiled"] is False
        assert spec["name"] == "triage-builder"
        assert spec["nodes"] == ["router", "writer"]
        assert spec["edges"] == [["START", "router"], ["router", "writer"], ["writer", "END"]]
        assert spec["schemas"]["state"].endswith("FakeState")

    def test_compile_and_register_uses_compiled_graph_builder(self, tmp_path):
        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangGraphAdapter(client=client)
        builder = FakeBuilder()

        compiled, passport_id = adapter.compile_and_register(
            builder,
            compile_kwargs={"debug": True, "name": "triage-runtime"},
            name="triage-graph",
            version="1.0.0",
            model_id="m" * 64,
            creator=CREATOR,
            system_prompt="Route tasks to the correct worker.",
        )

        agent = client.agents.get(passport_id)

        assert isinstance(compiled, FakeCompiledGraph)
        assert builder.compile_calls == [{"debug": True, "name": "triage-runtime"}]
        assert agent is not None
        assert agent.metadata["langgraph"]["graph_spec"]["compiled"] is True
        assert agent.metadata["langgraph"]["graph_spec"]["compile"]["debug"] is True
        assert agent.metadata["langgraph_runtime"]["compile"]["name"] == "triage-runtime"

    def test_bind_graph_registers_lazily_on_first_invoke(self, tmp_path):
        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangGraphAdapter(client=client)
        compiled = FakeCompiledGraph(FakeBuilder(), {})

        bound = adapter.bind_graph(
            compiled,
            name="lazy-graph",
            version="1.0.0",
            model_id="m" * 64,
            creator=CREATOR,
            system_prompt="Summarize before replying.",
        )

        assert isinstance(bound, BoundLangGraphRunnable)
        assert bound.passport_id is None

        result = bound.invoke({"question": "hello"})

        assert bound.passport_id is not None
        assert result["ok"] is True
        assert compiled.invoke_calls == [{"question": "hello"}]
        assert client.agents.get(bound.passport_id) is not None

    def test_real_langgraph_stategraph_compile_and_register(self, tmp_path):
        graph_module = pytest.importorskip("langgraph.graph")
        StateGraph = graph_module.StateGraph
        START = graph_module.START
        END = graph_module.END

        class State(TypedDict):
            value: int

        def increment(state: State) -> State:
            return {"value": state["value"] + 1}

        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangGraphAdapter(client=client)

        model_id = client.models.register(
            name="langgraph-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )

        builder = StateGraph(State)
        builder.add_node(increment)
        builder.add_edge(START, "increment")
        builder.add_edge("increment", END)

        compiled, passport_id = adapter.compile_and_register(
            builder,
            compile_kwargs={"name": "increment-runtime"},
            name="increment-graph",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            system_prompt="Increment the counter.",
        )

        result = compiled.invoke({"value": 1})
        agent = client.agents.get(passport_id)

        assert result["value"] == 2
        assert agent is not None
        assert agent.metadata["langgraph"]["graph_spec"]["compiled"] is True
        assert "increment" in agent.metadata["langgraph"]["graph_spec"]["nodes"]
        assert client.verify(passport_id)["valid"] is True
