"""HTTP sync receiver tests for the local service."""

from __future__ import annotations

import json

from fastapi.testclient import TestClient

from forkit.server import ServerSettings, create_app


MODEL_ID = "m" * 64
AGENT_ID = "a" * 64


class TestServerSync:
    def test_sync_passports_accepts_batch_and_persists_inbox_records(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "source": "local-dev",
            "target": "main-server",
            "after": 0,
            "cursor": 2,
            "has_more": False,
            "items": [
                {
                    "cursor": 1,
                    "operation": "upsert",
                    "passport_id": MODEL_ID,
                    "passport_type": "model",
                    "changed_at": "2026-03-27T12:00:00+00:00",
                    "document": {
                        "id": MODEL_ID,
                        "passport_type": "model",
                        "name": "demo-model",
                    },
                },
                {
                    "cursor": 2,
                    "operation": "delete",
                    "passport_id": AGENT_ID,
                    "passport_type": "agent",
                    "changed_at": "2026-03-27T12:01:00+00:00",
                    "document": None,
                },
            ],
        }

        with TestClient(create_app(settings=settings)) as client:
            response = client.post("/sync/passports", json=payload)

        assert response.status_code == 202
        body = response.json()
        assert body["status"] == "accepted"
        assert body["target"] == "main-server"
        assert body["source"] == "local-dev"
        assert body["cursor"] == 2
        assert body["accepted"] == 2
        assert body["stored_passports"] == 2

        batch_lines = (settings.registry_root / "sync_inbox.jsonl").read_text(encoding="utf-8").splitlines()
        assert len(batch_lines) == 1
        batch_record = json.loads(batch_lines[0])
        assert batch_record["target"] == "main-server"
        assert batch_record["items"][0]["passport_id"] == MODEL_ID

        model_lines = (
            settings.registry_root / "sync_inbox" / "main-server" / f"{MODEL_ID}.jsonl"
        ).read_text(encoding="utf-8").splitlines()
        agent_lines = (
            settings.registry_root / "sync_inbox" / "main-server" / f"{AGENT_ID}.jsonl"
        ).read_text(encoding="utf-8").splitlines()

        assert len(model_lines) == 1
        assert len(agent_lines) == 1
        assert json.loads(model_lines[0])["item"]["operation"] == "upsert"
        assert json.loads(agent_lines[0])["item"]["operation"] == "delete"

    def test_sync_passports_rejects_invalid_payload(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "source": "local-dev",
            "target": "main-server",
            "after": 0,
            "cursor": 1,
            "has_more": False,
            "items": [
                {
                    "cursor": 1,
                    "operation": "upsert",
                    "passport_id": MODEL_ID,
                    "passport_type": "model",
                    "changed_at": "2026-03-27T12:00:00+00:00",
                    "document": None,
                }
            ],
        }

        with TestClient(create_app(settings=settings)) as client:
            response = client.post("/sync/passports", json=payload)

        assert response.status_code == 422
        assert "document" in response.json()["detail"]

    def test_sync_passports_enforces_bearer_token_when_configured(self, tmp_path):
        settings = ServerSettings(
            registry_root=tmp_path / "registry",
            sync_bearer_token="secret-token",
        )
        payload = {
            "source": "local-dev",
            "target": "main-server",
            "after": 0,
            "cursor": 1,
            "has_more": False,
            "items": [
                {
                    "cursor": 1,
                    "operation": "delete",
                    "passport_id": MODEL_ID,
                    "passport_type": "model",
                    "changed_at": "2026-03-27T12:00:00+00:00",
                    "document": None,
                }
            ],
        }

        with TestClient(create_app(settings=settings)) as client:
            missing = client.post("/sync/passports", json=payload)
            wrong = client.post(
                "/sync/passports",
                json=payload,
                headers={"Authorization": "Bearer wrong-token"},
            )
            accepted = client.post(
                "/sync/passports",
                json=payload,
                headers={"Authorization": "Bearer secret-token"},
            )

        assert missing.status_code == 401
        assert wrong.status_code == 401
        assert accepted.status_code == 202
