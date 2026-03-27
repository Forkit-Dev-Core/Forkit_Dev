"""Bootstrap tests for the local FastAPI service."""

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from forkit.cli.main import app
from forkit.server import ServerSettings, create_app
from forkit_core.server import ServerSettings as CompatibilitySettings
from forkit_core.server import create_app as compatibility_create_app


class TestServerBootstrap:
    def test_legacy_server_namespace_uses_canonical_exports(self):
        assert CompatibilitySettings is ServerSettings
        assert compatibility_create_app is create_app

    def test_app_bootstraps_registry_and_health_routes(self, tmp_path):
        settings = ServerSettings(registry_root=tmp_path / "registry")
        with TestClient(create_app(settings=settings)) as client:
            root = client.get("/")
            health = client.get("/healthz")
            ready = client.get("/readyz")

        assert root.status_code == 200
        assert health.status_code == 200
        assert ready.status_code == 200

        root_json = root.json()
        health_json = health.json()
        ready_json = ready.json()

        assert root_json["service"] == "forkit-local-service"
        assert root_json["registry"]["root"] == str(settings.registry_root)
        assert root_json["registry"]["outbox_path"] == str(settings.registry_root / "outbox.jsonl")
        assert root_json["registry"]["sync_state_path"] == str(settings.registry_root / "sync_state.json")
        assert root_json["registry"]["sync_batches_path"] == str(settings.registry_root / "sync_inbox.jsonl")
        assert root_json["registry"]["sync_inbox_dir"] == str(settings.registry_root / "sync_inbox")
        assert root_json["sync"]["backend"] == "local"
        assert root_json["sync"]["auth_enabled"] is False
        assert root_json["sync"]["postgres_schema"] is None
        assert health_json["status"] == "ok"
        assert health_json["initialized"] is True
        assert ready_json["status"] == "ready"
        assert ready_json["index_db_exists"] is True
        assert ready_json["outbox_exists"] is True
        assert ready_json["sync_state_exists"] is True
        assert ready_json["sync_batches_exists"] is True
        assert ready_json["sync_inbox_exists"] is True

        assert (settings.registry_root / "models").exists()
        assert (settings.registry_root / "agents").exists()
        assert (settings.registry_root / "index.db").exists()
        assert (settings.registry_root / "outbox.jsonl").exists()
        assert (settings.registry_root / "sync_state.json").exists()
        assert (settings.registry_root / "sync_inbox.jsonl").exists()
        assert (settings.registry_root / "sync_inbox").exists()

    def test_serve_help_is_available(self):
        runner = CliRunner()
        result = runner.invoke(app, ["serve", "--help"])
        assert result.exit_code == 0
        assert "Run the local HTTP service over the registry." in result.stdout

    def test_invalid_sync_backend_is_rejected(self):
        with pytest.raises(ValueError, match="Unsupported sync backend"):
            ServerSettings(sync_backend="redis")
