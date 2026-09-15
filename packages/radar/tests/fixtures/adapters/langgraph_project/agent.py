"""Test-owned real framework graph with a deterministic model double; no API."""

from langchain.agents import create_agent
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from langchain_core.tools import tool


class ScriptedToolModel(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self


@tool
def add(a: int, b: int) -> int:
    """Add two integers."""
    return a + b


graph = create_agent(
    ScriptedToolModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[{"name": "add", "args": {"a": 2, "b": 3}, "id": "test-call"}],
            ),
            AIMessage(content="5"),
        ]
    ),
    tools=[add],
)
