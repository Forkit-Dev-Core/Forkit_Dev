"""Tests for the LangChain adapter."""

from typing import Any

import pytest

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_langchain import (
    BoundLangChainRunnable,
    ForkitLangChainCallbackHandler,
    LangChainAdapter,
)


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


class TestLangChainAdapter:
    def test_register_runnable_uses_runnable_hash_as_artifact_hash(self, tmp_path):
        runnable_module = pytest.importorskip("langchain_core.runnables")
        RunnableLambda = runnable_module.RunnableLambda

        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangChainAdapter(client=client)

        model_id = client.models.register(
            name="langchain-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )
        runnable = RunnableLambda(lambda payload: {"value": payload["value"] + 1})

        agent_id = adapter.register_runnable(
            runnable,
            name="increment-runnable",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            system_prompt="Increment the incoming value.",
        )

        agent = client.agents.get(agent_id)
        runnable_spec = adapter.extract_runnable_spec(runnable)
        runnable_hash = adapter.hash_runnable(runnable_spec)

        assert agent is not None
        assert agent.artifact_hash == runnable_hash
        assert agent.metadata["langchain"]["runnable_hash"] == runnable_hash
        assert agent.metadata["langchain"]["runnable_spec"]["name"] == "RunnableLambda"
        assert agent.metadata["langchain_runtime"]["bound_type"].endswith("RunnableLambda")
        assert client.verify(agent_id)["valid"] is True

    def test_bind_runnable_registers_lazily_and_captures_runtime(self, tmp_path):
        runnable_module = pytest.importorskip("langchain_core.runnables")
        RunnableLambda = runnable_module.RunnableLambda

        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangChainAdapter(client=client)
        model_id = client.models.register(
            name="langchain-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )
        runnable = RunnableLambda(lambda payload: {"value": payload["value"] + 1})

        bound = adapter.bind_runnable(
            runnable,
            name="lazy-increment",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            system_prompt="Increment the incoming value.",
        )

        assert isinstance(bound, BoundLangChainRunnable)
        assert bound.passport_id is None

        result = bound.invoke({"value": 1})
        summary = bound.runtime_summary()

        assert result["value"] == 2
        assert bound.passport_id is not None
        assert summary["passport_id"] == bound.passport_id
        assert summary["counts"]["chain_start"] >= 1
        assert summary["counts"]["chain_end"] >= 1
        assert "forkit" in summary["tags"]
        assert client.agents.get(bound.passport_id) is not None

    def test_merge_runtime_config_appends_callback_and_metadata(self, tmp_path):
        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangChainAdapter(client=client)
        callback = ForkitLangChainCallbackHandler()

        config = adapter.merge_runtime_config(
            {"tags": ["demo"], "metadata": {"source": "test"}},
            callback_handler=callback,
            passport_id="p" * 64,
        )

        assert "forkit" in config["tags"]
        assert config["metadata"]["source"] == "test"
        assert config["metadata"]["forkit_framework"] == "langchain"
        assert config["metadata"]["forkit_passport_id"] == "p" * 64
        assert callback in config["callbacks"]

    def test_real_langchain_create_agent_bind_and_invoke(self, tmp_path):
        agents_module = pytest.importorskip("langchain.agents")
        fake_models = pytest.importorskip("langchain_core.language_models.fake_chat_models")

        create_agent = agents_module.create_agent
        FakeListChatModel = fake_models.FakeListChatModel

        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangChainAdapter(client=client)
        model_id = client.models.register(
            name="langchain-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )

        agent = create_agent(
            model=FakeListChatModel(responses=["hello there"]),
            system_prompt="Be concise.",
            name="demo-agent",
        )
        bound = adapter.bind_runnable(
            agent,
            name="demo-agent",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            system_prompt="Be concise.",
        )

        result = bound.invoke({"messages": [{"role": "user", "content": "say hi"}]})
        stored = client.agents.get(bound.passport_id)
        summary = bound.runtime_summary()

        assert stored is not None
        assert result["messages"][-1].content == "hello there"
        assert stored.metadata["langchain"]["runnable_spec"]["name"] == "demo-agent"
        assert stored.metadata["langchain"]["runnable_spec"]["graph"]["nodes"][1]["id"] == "model"
        assert stored.metadata["langchain"]["runnable_spec"]["langgraph"]["compiled"] is True
        assert summary["counts"]["chat_model_start"] >= 1
        assert "FakeListChatModel" in summary["models"]

    def test_tool_calling_agent_captures_tool_metadata_and_runtime(self, tmp_path):
        agents_module = pytest.importorskip("langchain.agents")
        chat_models = pytest.importorskip("langchain_core.language_models.chat_models")
        messages_module = pytest.importorskip("langchain_core.messages")
        tool_messages = pytest.importorskip("langchain_core.messages.tool")
        outputs_module = pytest.importorskip("langchain_core.outputs")
        tools_module = pytest.importorskip("langchain_core.tools")

        create_agent = agents_module.create_agent
        BaseChatModel = chat_models.BaseChatModel
        AIMessage = messages_module.AIMessage
        ToolMessage = messages_module.ToolMessage
        tool_call = tool_messages.tool_call
        ChatGeneration = outputs_module.ChatGeneration
        ChatResult = outputs_module.ChatResult
        tool = tools_module.tool

        class FakeToolCallingChatModel(BaseChatModel):
            bound_tool_names: tuple[str, ...] = ()

            @property
            def _llm_type(self) -> str:
                return "fake-tool-calling-chat-model"

            def bind_tools(self, tools, *, tool_choice=None, **kwargs):
                names = []
                for item in tools:
                    name = getattr(item, "name", None) or getattr(item, "__name__", None)
                    names.append(name or type(item).__name__)
                return self.model_copy(update={"bound_tool_names": tuple(names)})

            def _generate(
                self,
                messages: list[Any],
                stop=None,
                run_manager=None,
                **kwargs,
            ):
                if any(isinstance(message, ToolMessage) for message in messages):
                    message = AIMessage(content="service status: green")
                else:
                    message = AIMessage(
                        content="",
                        tool_calls=[
                            tool_call(
                                name=self.bound_tool_names[0],
                                args={"service": "api"},
                                id="call-1",
                            )
                        ],
                    )
                return ChatResult(generations=[ChatGeneration(message=message)])

        @tool
        def lookup_status(service: str) -> str:
            """Return the service status."""
            return f"{service}:green"

        client = ForkitClient(registry_root=tmp_path / "registry")
        adapter = LangChainAdapter(client=client)
        model_id = client.models.register(
            name="tool-langchain-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )

        bound = adapter.create_and_bind(
            model=FakeToolCallingChatModel(),
            tools=[lookup_status],
            system_prompt="Use tools when needed.",
            create_kwargs={"name": "ops-agent"},
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
        )

        result = bound.invoke({"messages": [{"role": "user", "content": "check api"}]})
        stored = client.agents.get(bound.passport_id)
        summary = bound.runtime_summary()

        assert stored is not None
        assert result["messages"][-1].content == "service status: green"
        assert stored.metadata["langchain"]["runnable_spec"]["tools"][0]["name"] == "lookup_status"
        assert stored.metadata["langchain_runtime"]["tool_names"] == ["lookup_status"]
        assert "tools" in stored.metadata["langchain"]["runnable_spec"]["langgraph"]["nodes"]
        assert summary["counts"]["tool_start"] >= 1
        assert summary["counts"]["tool_end"] >= 1
        assert "lookup_status" in summary["tools"]
