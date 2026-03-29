"""Tests for the local MCP service layer."""

from __future__ import annotations

import pytest

from forkit.mcp.server import ForkitMCPService, build_mcp_server
from forkit.sdk import ForkitClient
from forkit.schemas import AgentArchitecture, AgentTaskType, TaskType


CREATOR = {"name": "Forkit Demo", "organization": "Forkit OSS"}


class TestForkitMCPService:
    def test_service_reads_and_verifies_local_passports(self, tmp_path):
        registry_root = tmp_path / "registry"
        client = ForkitClient(registry_root=registry_root)
        service = ForkitMCPService(registry_root=registry_root)

        model_id = client.models.register(
            name="mcp-test-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
            status="active",
        )
        agent_id = client.agents.register(
            name="mcp-test-agent",
            version="1.0.0",
            model_id=model_id,
            task_type=AgentTaskType.CODE_ASSISTANT,
            architecture=AgentArchitecture.REACT,
            creator=CREATOR,
            status="active",
        )

        passport = service.get_passport(model_id)
        verification = service.verify_passport(model_id)
        lineage = service.get_lineage(agent_id)
        search = service.search_registry(query="mcp-test", limit=10)

        assert passport["id"] == model_id
        assert verification["valid"] is True
        assert lineage["ancestors"][0]["id"] == model_id
        assert search["returned"] == 2

    def test_create_draft_passport_preserves_deterministic_identity_contract(self, tmp_path):
        service = ForkitMCPService(registry_root=tmp_path / "registry")

        draft = service.create_draft_passport(
            passport_type="model",
            name="draft-model",
            version="0.1.0",
            creator_name="Forkit Demo",
            creator_organization="Forkit OSS",
        )

        assert draft["passport_type"] == "model"
        assert draft["status"] == "draft"
        assert len(draft["id"]) == 64

    def test_agent_draft_requires_model_id(self, tmp_path):
        service = ForkitMCPService(registry_root=tmp_path / "registry")

        with pytest.raises(ValueError, match="model_id"):
            service.create_draft_passport(
                passport_type="agent",
                name="draft-agent",
                version="0.1.0",
                creator_name="Forkit Demo",
            )

    def test_build_server_requires_optional_mcp_dependency(self, tmp_path):
        try:
            import mcp.server.fastmcp  # noqa: F401
        except ImportError:
            with pytest.raises(ImportError, match="forkit-core\\[mcp\\]"):
                build_mcp_server(registry_root=tmp_path / "registry")
            return

        server = build_mcp_server(registry_root=tmp_path / "registry")
        assert server is not None
