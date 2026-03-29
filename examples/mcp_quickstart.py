"""
MCP tool-surface quickstart example.

Run: python examples/mcp_quickstart.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.mcp.server import ForkitMCPService
from forkit.sdk import ForkitClient
from forkit.schemas import AgentArchitecture, AgentTaskType, TaskType


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="forkit-mcp-") as tmpdir:
        client = ForkitClient(registry_root=tmpdir)
        service = ForkitMCPService(registry_root=tmpdir)

        model_id = client.models.register(
            name="mcp-demo-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator={"name": "Forkit Demo", "organization": "Forkit OSS"},
            status="active",
        )
        agent_id = client.agents.register(
            name="mcp-demo-agent",
            version="1.0.0",
            model_id=model_id,
            task_type=AgentTaskType.CODE_ASSISTANT,
            architecture=AgentArchitecture.REACT,
            creator={"name": "Forkit Demo", "organization": "Forkit OSS"},
            status="active",
            system_prompt="You validate deterministic passports.",
        )

        search = service.search_registry(query="mcp-demo", limit=10)
        passport = service.get_passport(model_id)
        verification = service.verify_passport(model_id)
        lineage = service.get_lineage(agent_id)
        draft = service.create_draft_passport(
            passport_type="model",
            name="draft-mcp-model",
            version="0.1.0",
            creator_name="Forkit Demo",
            creator_organization="Forkit OSS",
        )

        print(
            json.dumps(
                {
                    "search_results": search["returned"],
                    "passport_name": passport["name"],
                    "verify_valid": verification["valid"],
                    "ancestor_count": len(lineage["ancestors"]),
                    "draft_passport_id": draft["id"],
                },
                indent=2,
            )
        )


if __name__ == "__main__":
    main()
