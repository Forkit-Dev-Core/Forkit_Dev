"""Tests for the remote sync bridge and SDK sync surface."""

from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from typing import Any

import pytest

from forkit.sdk import ForkitClient
from forkit.schemas import AgentArchitecture, AgentTaskType, TaskType


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


def _start_sync_server(*, status_code: int = 200) -> tuple[str, list[dict[str, Any]], ThreadingHTTPServer, Thread]:
    requests: list[dict[str, Any]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self) -> None:  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            raw_body = self.rfile.read(length).decode("utf-8")
            payload = json.loads(raw_body)
            requests.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers.items()),
                    "payload": payload,
                }
            )

            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            response = {"accepted": len(payload.get("items", [])), "cursor": payload.get("cursor")}
            if status_code >= 400:
                response = {"error": "sync_failed"}
            self.wfile.write(json.dumps(response).encode("utf-8"))

        def log_message(self, format: str, *args: Any) -> None:  # noqa: A003
            return

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}/sync/passports"
    return url, requests, server, thread


def _stop_sync_server(server: ThreadingHTTPServer, thread: Thread) -> None:
    server.shutdown()
    server.server_close()
    thread.join(timeout=5)


class TestSyncBridge:
    def test_sync_push_batches_changes_and_persists_cursor(self, tmp_path):
        client = ForkitClient(registry_root=tmp_path / "registry")
        model_id = client.models.register(
            name="sync-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )
        client.agents.register(
            name="sync-agent",
            version="1.0.0",
            model_id=model_id,
            task_type=AgentTaskType.CUSTOMER_SUPPORT,
            architecture=AgentArchitecture.REACT,
            creator=CREATOR,
            system_prompt="Route tickets to the right queue.",
        )

        url, requests, server, thread = _start_sync_server()
        try:
            first = client.sync.push(url, target="main-server", limit=1, token="secret-token")
            second = client.sync.push(url, target="main-server", limit=1, token="secret-token")
        finally:
            _stop_sync_server(server, thread)

        assert first["status"] == "synced"
        assert first["cursor"] == 2
        assert first["batches"] == 2
        assert first["items_pushed"] == 2
        assert second["status"] == "idle"
        assert second["cursor"] == 2
        assert second["items_pushed"] == 0

        assert len(requests) == 2
        assert requests[0]["path"] == "/sync/passports"
        assert requests[0]["headers"]["Authorization"] == "Bearer secret-token"
        assert requests[0]["payload"]["after"] == 0
        assert requests[0]["payload"]["cursor"] == 1
        assert requests[1]["payload"]["after"] == 1
        assert requests[1]["payload"]["cursor"] == 2

        status = client.sync.status()
        assert client.sync.cursor("main-server") == 2
        assert status["main-server"]["endpoint"] == url
        assert status["main-server"]["metadata"]["last_batch_size"] == 1

    def test_sync_push_does_not_advance_cursor_on_http_error(self, tmp_path):
        client = ForkitClient(registry_root=tmp_path / "registry")
        client.models.register(
            name="sync-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )

        url, requests, server, thread = _start_sync_server(status_code=500)
        try:
            with pytest.raises(RuntimeError, match="HTTP 500"):
                client.sync.push(url, target="main-server")
        finally:
            _stop_sync_server(server, thread)

        assert len(requests) == 1
        assert client.sync.cursor("main-server") == 0
        assert client.sync.status() == {}
