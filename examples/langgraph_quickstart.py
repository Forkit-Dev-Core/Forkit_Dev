"""
Minimal LangGraph adapter quickstart.

Run: python examples/langgraph_quickstart.py
"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_langgraph import LangGraphAdapter

REGISTRY_ROOT = "/tmp/forkit-langgraph-demo"
CREATOR = {"name": "Hamza", "organization": "ForkIt"}

client = ForkitClient(registry_root=REGISTRY_ROOT)
adapter = LangGraphAdapter(client=client)

model_id = client.models.register(
    name="langgraph-base-model",
    version="1.0.0",
    task_type=TaskType.TEXT_GENERATION,
    architecture="transformer",
    creator=CREATOR,
)

agent_id = adapter.register_agent(
    name="triage-graph",
    version="1.0.0",
    model_id=model_id,
    creator=CREATOR,
    system_prompt="Route incoming tickets to billing or support.",
    graph_spec={
        "entrypoint": "router",
        "nodes": ["router", "billing", "support"],
        "edges": [["router", "billing"], ["router", "support"]],
    },
)

agent = client.agents.get(agent_id)
print(f"Graph agent: {agent_id[:16]}...")
print(f"Artifact hash: {agent.artifact_hash}")
print(f"Graph hash: {agent.metadata['langgraph']['graph_hash']}")
