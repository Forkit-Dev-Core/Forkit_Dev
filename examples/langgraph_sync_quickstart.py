"""
LangGraph registration and self-host sync demo.

Run: python examples/langgraph_sync_quickstart.py
"""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import sys
import tempfile
from threading import Thread
from typing import Any, TypedDict
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_langgraph import LangGraphAdapter

try:
    from langgraph.graph import END, START, StateGraph
except ImportError as exc:  # pragma: no cover - exercised by users without extra
    raise SystemExit(
        "This example requires the optional langgraph dependency.\n"
        "Install with:\n"
        "  pip install 'forkit-core[langgraph]'"
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


class TicketState(TypedDict):
    ticket: str
    queue: str


def route_ticket(state: TicketState) -> TicketState:
    ticket = state.get("ticket", "")
    queue = "priority" if "urgent" in ticket.lower() else "general"
    return {
        "ticket": ticket,
        "queue": queue,
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forkit-langgraph-sync-") as temp_dir:
        root = Path(temp_dir)
        source = ForkitClient(registry_root=root / "source")
        mirror = ForkitClient(registry_root=root / "mirror")
        adapter = LangGraphAdapter(client=source)

        model_id = source.models.register(
            name="langgraph-sync-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )

        builder = StateGraph(TicketState)
        builder.add_node("route_ticket", route_ticket)
        builder.add_edge(START, "route_ticket")
        builder.add_edge("route_ticket", END)

        compiled, passport_id = adapter.compile_and_register(
            builder,
            compile_kwargs={"name": "ticket-router-runtime"},
            name="ticket-router-graph",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            system_prompt="Route incoming tickets into the correct queue.",
        )

        result = compiled.invoke({"ticket": "Urgent customer escalation", "queue": ""})

        export_url, export_server, export_thread = _start_export_server(source)
        try:
            pull_result = mirror.sync.pull(
                export_url,
                source="langgraph-source",
            )
        finally:
            _stop_server(export_server, export_thread)

        mirrored_agent = mirror.get_agent(passport_id)
        summary = {
            "source_registry": str(source.registry.root),
            "mirror_registry": str(mirror.registry.root),
            "passport_id": passport_id,
            "invoke_queue": result["queue"],
            "pull_status": pull_result["status"],
            "pull_items": pull_result["items_applied"],
            "mirror_total": mirror.stats()["total"],
            "mirror_outbox_items": len(mirror.sync.export()["items"]),
            "mirrored_agent_present": mirrored_agent is not None,
            "mirrored_graph_name": (
                mirrored_agent.metadata["langgraph"]["graph_spec"]["name"]
                if mirrored_agent is not None
                else None
            ),
            "mirrored_nodes": (
                mirrored_agent.metadata["langgraph"]["graph_spec"]["nodes"]
                if mirrored_agent is not None
                else []
            ),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
