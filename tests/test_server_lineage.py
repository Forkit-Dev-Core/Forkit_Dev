"""HTTP lineage tests for the local service."""

from fastapi.testclient import TestClient

from forkit.server import ServerSettings, create_app


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


class TestServerLineage:
    def test_get_lineage_returns_ancestors_and_descendants(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        base_model = {
            "name": "base-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }
        ft_model = {
            "name": "ft-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }
        agent = {
            "name": "support-agent",
            "version": "1.0.0",
            "task_type": "customer-support",
            "architecture": "ReAct",
            "creator": CREATOR,
            "system_prompt": "You are a helpful support assistant.",
        }

        with TestClient(create_app(settings=settings)) as client:
            base = client.post("/models", json=base_model).json()
            ft_model["base_model_id"] = base["id"]
            ft = client.post("/models", json=ft_model).json()
            agent["model_id"] = ft["id"]
            created_agent = client.post("/agents", json=agent).json()

            response = client.get(f"/lineage/{ft['id']}")

        assert response.status_code == 200
        body = response.json()
        assert body["node"]["id"] == ft["id"]
        assert body["direction"] == "both"

        ancestor_ids = {node["id"] for node in body["ancestors"]}
        descendant_ids = {node["id"] for node in body["descendants"]}

        assert base["id"] in ancestor_ids
        assert created_agent["id"] in descendant_ids

    def test_get_lineage_supports_direction_filter(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        model = {
            "name": "demo-model",
            "version": "1.0.0",
            "task_type": "text-generation",
            "architecture": "transformer",
            "creator": CREATOR,
        }

        with TestClient(create_app(settings=settings)) as client:
            created = client.post("/models", json=model).json()
            response = client.get(f"/lineage/{created['id']}?direction=ancestors")

        assert response.status_code == 200
        body = response.json()
        assert body["direction"] == "ancestors"
        assert body["ancestors"] == []
        assert body["descendants"] == []

    def test_get_lineage_returns_not_found_error(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")

        with TestClient(create_app(settings=settings)) as client:
            response = client.get(f"/lineage/{'c' * 64}")

        assert response.status_code == 404
        assert response.json() == {
            "error": {
                "code": "not_found",
                "message": "Passport not found.",
                "passport_id": "c" * 64,
            }
        }
