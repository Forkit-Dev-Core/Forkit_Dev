"""HTTP export tests for the local service."""

from fastapi.testclient import TestClient

from forkit.server import ServerSettings, create_app


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


class TestServerExport:
    def test_export_returns_cursor_ordered_documents(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        model = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }
        agent = {
            "name": "demo-agent",
            "version": "1.0.0",
            "task_type": "customer-support",
            "architecture": "ReAct",
            "creator": CREATOR,
            "system_prompt": "You are a helpful support assistant.",
        }

        with TestClient(create_app(settings=settings)) as client:
            created_model = client.post("/models", json=model).json()
            agent["model_id"] = created_model["id"]
            created_agent = client.post("/agents", json=agent).json()

            response = client.get("/export")

        assert response.status_code == 200
        body = response.json()
        assert body["cursor"] == 2
        assert body["has_more"] is False
        assert [item["passport_id"] for item in body["items"]] == [
            created_model["id"],
            created_agent["id"],
        ]
        assert body["items"][0]["document"]["id"] == created_model["id"]
        assert body["items"][1]["document"]["id"] == created_agent["id"]

    def test_export_supports_after_limit_and_type_filter(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        model_one = {
            "name": "model-one",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }
        model_two = {
            "name": "model-two",
            "version": "2.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }
        agent = {
            "name": "demo-agent",
            "version": "1.0.0",
            "task_type": "customer-support",
            "architecture": "ReAct",
            "creator": CREATOR,
            "system_prompt": "Route tickets to the right queue.",
        }

        with TestClient(create_app(settings=settings)) as client:
            first = client.post("/models", json=model_one).json()
            second = client.post("/models", json=model_two).json()
            agent["model_id"] = second["id"]
            created_agent = client.post("/agents", json=agent).json()

            first_page = client.get("/export?limit=1")
            second_page = client.get("/export?after=1&passport_type=agent")

        assert first_page.status_code == 200
        assert second_page.status_code == 200

        first_body = first_page.json()
        second_body = second_page.json()

        assert first_body["cursor"] == 1
        assert first_body["has_more"] is True
        assert len(first_body["items"]) == 1
        assert first_body["items"][0]["passport_id"] == first["id"]

        assert second_body["cursor"] == 3
        assert second_body["has_more"] is False
        assert [item["passport_id"] for item in second_body["items"]] == [created_agent["id"]]
