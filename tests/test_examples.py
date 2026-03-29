"""Smoke tests for runnable example scripts."""

from __future__ import annotations

import json
import runpy
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestExamples:
    def test_minimal_local_passport_runs(self, capsys):
        runpy.run_path(
            str(REPO_ROOT / "examples" / "minimal_local_passport.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["name"] == "hello-local-model"
        assert payload["passport_type"] == "model"
        assert payload["valid"] is True
        assert payload["models"] == 1
        assert payload["agents"] == 0

    def test_cli_quickstart_runs(self, capsys):
        pytest.importorskip("typer.testing")
        runpy.run_path(
            str(REPO_ROOT / "examples" / "cli_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["list_contains_model"] is True
        assert payload["verify_valid"] is True
        assert payload["stats"] == {"models": 1, "agents": 0}

    def test_github_ci_quickstart_runs(self, capsys):
        runpy.run_path(
            str(REPO_ROOT / "examples" / "github_ci_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["generated"] is True
        assert payload["validated"] is True
        assert payload["passport_path"] == "forkit-passport.json"
        assert payload["validator_summary"] == "Forkit passport is valid"

    def test_mcp_quickstart_runs(self, capsys):
        runpy.run_path(
            str(REPO_ROOT / "examples" / "mcp_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["search_results"] == 2
        assert payload["passport_name"] == "mcp-demo-model"
        assert payload["verify_valid"] is True
        assert payload["ancestor_count"] == 1
        assert len(payload["draft_passport_id"]) == 64

    def test_tamper_detection_demo_runs(self, capsys):
        runpy.run_path(
            str(REPO_ROOT / "examples" / "tamper_detection_demo.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["valid_before"] is True
        assert payload["valid_after"] is False
        assert payload["reason_after"] == "id_mismatch"
        assert payload["stored_id"] != payload["derived_after"]

    def test_self_host_sync_quickstart_runs(self, capsys):
        runpy.run_path(
            str(REPO_ROOT / "examples" / "self_host_sync_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["push_status"] == "synced"
        assert payload["pull_status"] == "synced"
        assert payload["push_items"] == 2
        assert payload["pull_items"] == 2
        assert payload["mirror_total"] == 2
        assert payload["mirror_outbox_items"] == 0
        assert payload["receiver_model_inbox_exists"] is True
        assert payload["mirror_model_present"] is True
        assert payload["mirror_agent_present"] is True

    def test_langgraph_sync_quickstart_runs(self, capsys):
        pytest.importorskip("langgraph.graph")

        runpy.run_path(
            str(REPO_ROOT / "examples" / "langgraph_sync_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["invoke_queue"] == "priority"
        assert payload["pull_status"] == "synced"
        assert payload["pull_items"] == 2
        assert payload["mirror_total"] == 2
        assert payload["mirror_outbox_items"] == 0
        assert payload["mirrored_agent_present"] is True
        assert payload["mirrored_graph_name"] == "ticket-router-runtime"
        assert "route_ticket" in payload["mirrored_nodes"]

    def test_langchain_sync_quickstart_runs(self, capsys):
        pytest.importorskip("langchain.agents")
        pytest.importorskip("langchain_core.tools")

        runpy.run_path(
            str(REPO_ROOT / "examples" / "langchain_sync_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["invoke_message"] == "service status: green"
        assert payload["pull_status"] == "synced"
        assert payload["pull_items"] == 2
        assert payload["mirror_total"] == 2
        assert payload["mirror_outbox_items"] == 0
        assert payload["mirrored_agent_present"] is True
        assert payload["mirrored_tool_names"] == ["lookup_status"]
        assert payload["runtime_counts"]["tool_start"] >= 1
        assert payload["runtime_counts"]["tool_end"] >= 1

    def test_openclaw_quickstart_runs(self, capsys):
        runpy.run_path(
            str(REPO_ROOT / "examples" / "openclaw_quickstart.py"),
            run_name="__main__",
        )

        output = capsys.readouterr().out
        payload = json.loads(output)

        assert payload["architecture"] == "Tool-Use"
        assert payload["tool_names"] == ["incident_lookup"]
        assert payload["plugin_name"] == "@forkit/openclaw-ops"
        assert payload["channel_names"] == ["matrix"]
        assert payload["hook_names"] == ["session-memory"]
