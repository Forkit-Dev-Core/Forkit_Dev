"""SDK contract tests for the canonical and compatibility namespaces."""

from forkit.sdk import ForkitClient as CanonicalClient
from forkit_core.sdk import ForkitClient as CompatibilityClient
from forkit.schemas import AgentArchitecture, AgentTaskType, TaskType


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


class TestSDKCompatibility:
    def test_legacy_namespace_uses_canonical_client(self):
        assert CompatibilityClient is CanonicalClient

    def test_fluent_clients_register_and_query(self, tmp_path):
        client = CanonicalClient(registry_root=tmp_path / "registry")

        model_id = client.models.register(
            name="demo-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )
        agent_id = client.agents.register(
            name="demo-agent",
            version="1.0.0",
            model_id=model_id,
            task_type=AgentTaskType.CUSTOMER_SUPPORT,
            architecture=AgentArchitecture.REACT,
            creator=CREATOR,
            system_prompt="You are a helpful support assistant.",
        )

        assert client.models.get(model_id) is not None
        assert client.agents.get(agent_id) is not None
        assert client.verify(model_id)["valid"] is True

        ancestors = client.lineage.ancestors(agent_id)
        assert len(ancestors) == 1
        assert ancestors[0]["id"] == model_id
