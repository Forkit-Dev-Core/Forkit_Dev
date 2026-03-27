"""
Minimal OpenClaw adapter quickstart.

Run: python examples/openclaw_quickstart.py
"""

from __future__ import annotations

import json
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_openclaw import OpenClawAdapter


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


def write_plugin(plugin_root: Path) -> None:
    (plugin_root / "hooks" / "session-memory").mkdir(parents=True)
    (plugin_root / "openclaw.plugin.json").write_text(
        json.dumps(
            {
                "name": "@forkit/openclaw-ops",
                "version": "1.0.0",
                "type": "module",
                "openclaw": {
                    "extensions": ["./index.ts"],
                },
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    (plugin_root / "index.ts").write_text(
        """
        import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

        export default definePluginEntry({
          id: "ops-plugin",
          name: "Ops Plugin",
          description: "Adds operational tooling to OpenClaw",
          register(api) {
            api.registerTool(
              {
                name: "incident_lookup",
                description: "Lookup incidents",
              },
              { optional: true },
            );
          },
        });
        """.strip(),
        encoding="utf-8",
    )
    (plugin_root / "hooks" / "session-memory" / "HOOK.md").write_text(
        """
        ---
        name: session-memory
        description: "Save session summaries"
        metadata: { "openclaw": { "events": ["command:new"] } }
        ---
        # Session Memory
        """.strip(),
        encoding="utf-8",
    )
    (plugin_root / "hooks" / "session-memory" / "handler.ts").write_text(
        "export default async function handler() {}",
        encoding="utf-8",
    )


def write_config(config_path: Path) -> None:
    config_path.write_text(
        """
        // OpenClaw gateway config
        {
          agents: {
            defaults: { workspace: "~/.openclaw/workspace" },
            entries: {
              ops: {
                model: "gpt-4.1",
                tools: { allow: ["incident_lookup"] },
              },
            },
          },
          channels: { matrix: { allowFrom: ["@ops:example.org"] } },
          tools: { allow: ["incident_lookup"] },
          hooks: { internal: { enabled: true } },
        }
        """.strip(),
        encoding="utf-8",
    )


if __name__ == "__main__":
    temp_root = Path(tempfile.mkdtemp(prefix="forkit-openclaw-demo-"))
    try:
        registry_root = temp_root / "registry"
        plugin_root = temp_root / "openclaw-ops"
        plugin_root.mkdir()
        config_path = temp_root / "openclaw.json"

        write_plugin(plugin_root)
        write_config(config_path)

        client = ForkitClient(registry_root=registry_root)
        adapter = OpenClawAdapter(client=client)

        model_id = client.models.register(
            name="openclaw-base-model",
            version="1.0.0",
            task_type=TaskType.TEXT_GENERATION,
            architecture="transformer",
            creator=CREATOR,
        )

        gateway_id = adapter.register_gateway(
            config_path,
            plugin_roots=[plugin_root],
            name="openclaw-ops-gateway",
            version="1.0.0",
            model_id=model_id,
            creator=CREATOR,
            system_prompt="Keep operational tools available.",
        )

        agent = client.agents.get(gateway_id)
        plugin_spec = agent.metadata["openclaw"]["agent_spec"]["plugins"][0]

        print(
            json.dumps(
                {
                    "gateway_id": gateway_id,
                    "artifact_hash": agent.artifact_hash,
                    "architecture": agent.architecture.value,
                    "tool_names": [tool.name for tool in agent.tools],
                    "plugin_name": plugin_spec["name"],
                    "channel_names": agent.metadata["openclaw"]["agent_spec"]["channels"],
                    "hook_names": [hook["name"] for hook in plugin_spec["hooks"]],
                },
                indent=2,
            )
        )
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
