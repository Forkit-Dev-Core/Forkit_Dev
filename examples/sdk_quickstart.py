"""
forkit-core SDK quickstart.

Run: python examples/sdk_quickstart.py
"""

from pathlib import Path
import sys

# Make the package importable when run from the repo root or examples/
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import AgentArchitecture, AgentTaskType, TaskType

client = ForkitClient(registry_root="/tmp/forkit-demo-registry")

# 1. Register a model
model_id = client.models.register(
    name="llama-3-8b-demo",
    version="1.0.0",
    task_type=TaskType.TEXT_GENERATION,
    architecture="transformer",
    creator={"name": "Hamza", "organization": "ForkIt"},
    parameter_count=8_000_000_000,
    license="llama3",
    tags=["demo", "llm"],
)
print(f"Model registered: {model_id[:16]}...")

# 2. Register an agent using that model
agent_id = client.agents.register(
    name="support-agent-demo",
    version="1.0.0",
    model_id=model_id,
    task_type=AgentTaskType.CUSTOMER_SUPPORT,
    architecture=AgentArchitecture.REACT,
    creator={"name": "Hamza", "organization": "ForkIt"},
    system_prompt="You are a helpful support assistant. Answer concisely.",
    temperature=0.3,
    tags=["demo", "support"],
)
print(f"Agent registered:  {agent_id[:16]}...")

# 3. Inspect
passport = client.models.get(model_id)
print(f"\nModel name    : {passport.name}")
print(f"Model version : {passport.version}")
print(f"Architecture  : {passport.architecture}")

# 4. Lineage
ancestors = client.lineage.ancestors(agent_id)
print(f"\nAgent ancestors: {len(ancestors)}")
for n in ancestors:
    print(f"  [{n['node_type']}] {n['name']} v{n['version']}")

# 5. Stats
stats = client.stats()
print(f"\nRegistry stats:")
print(f"  Models  : {stats['models']}")
print(f"  Agents  : {stats['agents']}")

# 6. Verify
result = client.verify(model_id)
print(f"\nVerification: {'✓ valid' if result['valid'] else '✗ invalid'}")
