"""
LangChain registration and self-host sync demo.

Run: python examples/langchain_sync_quickstart.py
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
from threading import Thread
from typing import Any
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_langchain import LangChainAdapter

try:
    from langchain_core.language_models.chat_models import BaseChatModel
    from langchain_core.messages import AIMessage, ToolMessage
    from langchain_core.messages.tool import tool_call
    from langchain_core.outputs import ChatGeneration, ChatResult
    from langchain_core.tools import tool
except ImportError as exc:  # pragma: no cover - exercised by users without extra
    raise SystemExit(
        "This example requires the optional langchain dependency.\n"
        "Install with:\n"
        "  pip install 'forkit-core[langchain]'"
    ) from exc


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


def _start_export_server(client: ForkitClient) -> tuple[str, ThreadingHTTPServer, Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/export":
                self.send_response(404)
                self.end_headers()
                return

            query = parse_qs(parsed.query)
            payload = client.sync.export(
                after=int(query.get("after", ["0"])[0]),
                limit=int(query.get("limit", ["100"])[0]),
                passport_type=query.get("passport_type", [None])[0],
            )

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(payload).encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}/export", server, thread


def _stop_server(server: ThreadingHTTPServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


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


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forkit-langchain-sync-") as temp_dir:
        root = Path(temp_dir)
        source = ForkitClient(registry_root=root / "source")
        mirror = ForkitClient(registry_root=root / "mirror")
        adapter = LangChainAdapter(client=source)

        model_id = source.models.register(
            name="langchain-sync-model",
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

        export_url, export_server, export_thread = _start_export_server(source)
        try:
            pull_result = mirror.sync.pull(
                export_url,
                source="langchain-source",
            )
        finally:
            _stop_server(export_server, export_thread)

        mirrored_agent = mirror.get_agent(bound.passport_id)
        summary = {
            "source_registry": str(source.registry.root),
            "mirror_registry": str(mirror.registry.root),
            "passport_id": bound.passport_id,
            "invoke_message": result["messages"][-1].content,
            "pull_status": pull_result["status"],
            "pull_items": pull_result["items_applied"],
            "mirror_total": mirror.stats()["total"],
            "mirror_outbox_items": len(mirror.sync.export()["items"]),
            "mirrored_agent_present": mirrored_agent is not None,
            "mirrored_tool_names": (
                mirrored_agent.metadata["langchain_runtime"]["tool_names"]
                if mirrored_agent is not None
                else []
            ),
            "runtime_counts": bound.runtime_summary()["counts"],
        }
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
