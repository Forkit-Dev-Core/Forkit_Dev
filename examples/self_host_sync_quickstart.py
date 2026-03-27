"""
Self-hosted sync demo for two local forkit registries.

Run: python examples/self_host_sync_quickstart.py
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
from forkit.schemas import AgentArchitecture, AgentTaskType, TaskType


CREATOR = {"name": "Hamza", "organization": "ForkIt"}
SYNC_TOKEN = "demo-sync-token"


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


def _start_receiver_server(
    client: ForkitClient,
    *,
    token: str | None = None,
) -> tuple[str, ThreadingHTTPServer, Thread]:
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/sync/passports":
                self.send_response(404)
                self.end_headers()
                return

            if token is not None and self.headers.get("Authorization") != f"Bearer {token}":
                self.send_response(401)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"error": "unauthorized"}).encode("utf-8"))
                return

            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            response = client.registry.ingest_sync_batch(payload)

            self.send_response(202)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(response).encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return f"http://127.0.0.1:{server.server_port}/sync/passports", server, thread


def _stop_server(server: ThreadingHTTPServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forkit-self-host-") as temp_dir:
        root = Path(temp_dir)
        source = ForkitClient(registry_root=root / "source")
        mirror = ForkitClient(registry_root=root / "mirror")

        model_id = source.models.register(
            name="shared-triage-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )
        agent_id = source.agents.register(
            name="shared-triage-agent",
            version="1.0.0",
            model_id=model_id,
            task_type=AgentTaskType.CUSTOMER_SUPPORT,
            architecture=AgentArchitecture.REACT,
            creator=CREATOR,
            system_prompt="Route support work to the right queue.",
        )

        export_url, export_server, export_thread = _start_export_server(source)
        receiver_url, receiver_server, receiver_thread = _start_receiver_server(
            mirror,
            token=SYNC_TOKEN,
        )
        try:
            push_result = source.sync.push(
                receiver_url,
                target="mirror-inbox",
                token=SYNC_TOKEN,
            )
            pull_result = mirror.sync.pull(
                export_url,
                source="source-registry",
            )
        finally:
            _stop_server(export_server, export_thread)
            _stop_server(receiver_server, receiver_thread)

        inbox_dir = mirror.registry.sync_inbox_dir / "mirror-inbox"
        summary = {
            "source_registry": str(source.registry.root),
            "mirror_registry": str(mirror.registry.root),
            "push_status": push_result["status"],
            "push_items": push_result["items_pushed"],
            "pull_status": pull_result["status"],
            "pull_items": pull_result["items_applied"],
            "mirror_total": mirror.stats()["total"],
            "mirror_outbox_items": len(mirror.sync.export()["items"]),
            "receiver_batches_path": str(mirror.registry.sync_batches_path),
            "receiver_model_inbox_exists": (inbox_dir / f"{model_id}.jsonl").exists(),
            "mirror_model_present": mirror.get_model(model_id) is not None,
            "mirror_agent_present": mirror.get_agent(agent_id) is not None,
        }
        print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
