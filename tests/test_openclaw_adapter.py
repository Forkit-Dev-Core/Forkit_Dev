"""Tests for the OpenClaw adapter."""

from __future__ import annotations

from pathlib import Path

from forkit.sdk import ForkitClient
from forkit.schemas import TaskType
from forkit_openclaw import OpenClawAdapter


CREATOR = {"name": "Hamza", "organization": "ForkIt"}


def _write_openclaw_plugin(plugin_root: Path) -> None:
    (plugin_root / "hooks" / "session-memory").mkdir(parents=True)

    (plugin_root / "openclaw.plugin.json").write_text(
        """
        {
          "name": "@forkit/openclaw-ops",
          "version": "1.0.0",
          "type": "module",
          "openclaw": {
            "extensions": ["./index.ts"]
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (plugin_root / "package.json").write_text(
        """
        {
          "name": "@forkit/openclaw-ops",
          "version": "1.0.0",
          "openclaw": {
            "extensions": ["./index.ts"]
          }
        }
        """.strip(),
        encoding="utf-8",
    )
    (plugin_root / "index.ts").write_text(
        """
        import { definePluginEntry } from "openclaw/plugin-sdk/plugin-entry";

        export default definePluginEntry({
          id: "ops-plugin",
          name: "Ops Plugin",
          description: "Adds OpenClaw ops tooling",
          register(api) {
            api.registerTool(
              {
                name: "incident_lookup",
                description: "Lookup incidents",
              },
              { optional: true },
            );
            api.registerCommand({
              name: "ops_status",
              description: "Show ops status",
            });
          },
        });
        """.strip(),
        encoding="utf-8",
    )
    (plugin_root / "AGENTS.md").write_text("# AGENTS\n", encoding="utf-8")
    (plugin_root / "hooks" / "session-memory" / "HOOK.md").write_text(
        """
        ---
        name: session-memory
        description: "Save workspace memory snapshots"
        metadata: { "openclaw": { "events": ["command:new", "command:reset"] } }
        ---
        # Session Memory
        """.strip(),
        encoding="utf-8",
    )
    (plugin_root / "hooks" / "session-memory" / "handler.ts").write_text(
        "export default async function handler() {}",
        encoding="utf-8",
    )


class TestOpenClawAdapter:
    def test_extract_plugin_spec_reads_manifest_extensions_and_hooks(self, tmp_path):
        plugin_root = tmp_path / "openclaw-ops"
        plugin_root.mkdir()
        _write_openclaw_plugin(plugin_root)

        adapter = OpenClawAdapter(registry_root=tmp_path / "registry")
        spec = adapter.extract_plugin_spec(plugin_root)

        assert spec["name"] == "@forkit/openclaw-ops"
        assert spec["plugin_entry"]["id"] == "ops-plugin"
        assert spec["extensions"][0]["path"] == "./index.ts"
        assert spec["extensions"][0]["registers"]["tools"][0]["name"] == "incident_lookup"
        assert spec["extensions"][0]["registers"]["tools"][0]["optional"] is True
        assert spec["hooks"][0]["name"] == "session-memory"
        assert spec["hooks"][0]["events"] == ["command:new", "command:reset"]
        assert spec["bootstrap_files"] == ["AGENTS.md"]

    def test_extract_gateway_spec_parses_json5_like_config(self, tmp_path):
        plugin_root = tmp_path / "openclaw-ops"
        plugin_root.mkdir()
        _write_openclaw_plugin(plugin_root)

        config_path = tmp_path / "openclaw.json"
        config_path.write_text(
            """
            // OpenClaw gateway config
            {
              agents: {
                defaults: { workspace: "~/.openclaw/workspace", heartbeat: { every: "2h" } },
                entries: {
                  ops: {
                    model: "gpt-4.1",
                    tools: { allow: ["incident_lookup"] },
                  },
                },
              },
              channels: { matrix: { allowFrom: ["@ops:example.org"] } },
              tools: { allow: ["incident_lookup"] },
              plugins: {
                entries: {
                  ops_plugin: {
                    package: "@forkit/openclaw-ops",
                    enabled: true,
                  },
                },
              },
              hooks: { internal: { enabled: true } },
            }
            """.strip(),
            encoding="utf-8",
        )

        adapter = OpenClawAdapter(registry_root=tmp_path / "registry")
        spec = adapter.extract_gateway_spec(config_path, plugin_roots=[plugin_root])

        assert spec["framework"] == "openclaw"
        assert spec["config_file"] == "openclaw.json"
        assert spec["agent_defaults"]["workspace"] == "~/.openclaw/workspace"
        assert spec["agents"][0]["name"] == "ops"
        assert spec["agents"][0]["tool_allow"] == ["incident_lookup"]
        assert spec["channels"] == ["matrix"]
        assert spec["plugins"][0]["name"] == "@forkit/openclaw-ops"
        assert spec["plugin_entries"][0]["package"] == "@forkit/openclaw-ops"
        assert spec["hooks"]["internal_enabled"] is True

    def test_register_gateway_uses_openclaw_spec_hash_and_tool_refs(self, tmp_path):
        plugin_root = tmp_path / "openclaw-ops"
        plugin_root.mkdir()
        _write_openclaw_plugin(plugin_root)

        config_path = tmp_path / "openclaw.json"
        config_path.write_text(
            """
            {
              agents: {
                entries: {
                  ops: {
                    model: "gpt-4.1",
                    tools: { allow: ["incident_lookup"] },
                  },
                },
              },
              tools: { allow: ["incident_lookup"] },
            }
            """.strip(),
            encoding="utf-8",
        )

        client = ForkitClient(registry_root=tmp_path / "registry")
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
            system_prompt="Keep operational tooling available.",
        )

        agent = client.agents.get(gateway_id)
        spec = adapter.extract_gateway_spec(config_path, plugin_roots=[plugin_root])
        spec_hash = adapter.hash_agent_spec(spec)

        assert agent is not None
        assert agent.artifact_hash == spec_hash
        assert agent.metadata["openclaw"]["agent_hash"] == spec_hash
        assert agent.metadata["openclaw"]["agent_spec"]["framework"] == "openclaw"
        assert agent.tools[0].name == "incident_lookup"
        assert agent.capabilities.supports_tool_use is True
        assert agent.architecture.value == "Tool-Use"
        assert client.verify(gateway_id)["valid"] is True
