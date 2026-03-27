"""HTTP registration tests for model and agent endpoints."""

import json

from fastapi.testclient import TestClient

from forkit.server import ServerSettings, create_app


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


class TestServerRegistration:
    def test_get_passport_returns_registered_model(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }

        with TestClient(create_app(settings=settings)) as client:
            created = client.post("/models", json=payload)
            fetched = client.get(f"/passports/{created.json()['id']}")

        assert created.status_code == 201
        assert fetched.status_code == 200
        assert fetched.json()["id"] == created.json()["id"]
        assert fetched.json()["passport_type"] == "model"

    def test_get_passport_returns_not_found_error(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")

        with TestClient(create_app(settings=settings)) as client:
            response = client.get(f"/passports/{'a' * 64}")

        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "code": "not_found",
                "message": "Passport not found.",
                "passport_id": "a" * 64,
            }
        }

    def test_post_models_registers_model_passport(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }

        with TestClient(create_app(settings=settings)) as client:
            response = client.post("/models", json=payload)

        assert response.status_code == 201
        body = response.json()
        assert body["passport_type"] == "model"
        assert body["name"] == payload["name"]
        assert len(body["id"]) == 64

    def test_post_agents_registers_agent_passport(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        model_payload = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }
        agent_payload = {
            "name": "demo-agent",
            "version": "1.0.0",
            "task_type": "customer-support",
            "architecture": "ReAct",
            "creator": CREATOR,
            "system_prompt": "You are a helpful support assistant.",
        }

        with TestClient(create_app(settings=settings)) as client:
            model_response = client.post("/models", json=model_payload)
            agent_payload["model_id"] = model_response.json()["id"]
            agent_response = client.post("/agents", json=agent_payload)

        assert model_response.status_code == 201
        assert agent_response.status_code == 201

        body = agent_response.json()
        assert body["passport_type"] == "agent"
        assert body["model_id"] == agent_payload["model_id"]
        assert body["system_prompt"]["length_chars"] == len(agent_payload["system_prompt"])
        assert len(body["system_prompt"]["hash"]) == 64

    def test_post_models_rejects_invalid_payload(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "name": "broken-model",
            "version": "1.0.0",
            "architecture": "transformer",
            "creator": CREATOR,
        }

        with TestClient(create_app(settings=settings)) as client:
            response = client.post("/models", json=payload)

        assert response.status_code == 422

    def test_verify_passport_returns_valid_result(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }

        with TestClient(create_app(settings=settings)) as client:
            created = client.post("/models", json=payload)
            verified = client.post(f"/verify/{created.json()['id']}")

        assert created.status_code == 201
        assert verified.status_code == 200
        body = verified.json()
        assert body["valid"] is True
        assert body["stored_id"] == created.json()["id"]

    def test_verify_passport_returns_not_found_error(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")

        with TestClient(create_app(settings=settings)) as client:
            response = client.post(f"/verify/{'b' * 64}")

        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "code": "not_found",
                "message": "Passport not found.",
                "passport_id": "b" * 64,
            }
        }

    def test_verify_passport_detects_tampering(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        payload = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }

        with TestClient(create_app(settings=settings)) as client:
            created = client.post("/models", json=payload)
            passport_id = created.json()["id"]

            path = settings.registry_root / "models" / f"{passport_id}.json"
            tampered = json.loads(path.read_text())
            tampered["name"] = "tampered-model"
            path.write_text(json.dumps(tampered, indent=2))

            response = client.post(f"/verify/{passport_id}")

        assert response.status_code == 409
        body = response.json()
        assert body["error"]["code"] == "id_mismatch"
        assert body["error"]["passport_id"] == passport_id
        assert body["error"]["verification"]["valid"] is False
