"""Smoke tests for runnable example scripts."""

from __future__ import annotations

import json
import runpy
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent


class TestExamples:
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
