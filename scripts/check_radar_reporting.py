"""Installed-wheel reporting preview: consent, counts and privacy without networking."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from forkit_radar.reporting.contracts import Preview
from forkit_radar.reporting.storage import ReportingStore

from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []

    def no_network(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
            raise AssertionError("network_forbidden_for_local_preview")
    sys.addaudithook(no_network)
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="forkit-reporting-") as temporary:
        root = Path(temporary).resolve()
        project, store = root / "PRIVATE_PROJECT", root / "store"
        project.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
        registry = LocalRegistry(root / "registry")
        model = ModelPassport(name="PRIVATE_MODEL", version="1.0", creator={"name": "Fixture"}, task_type="text-generation", architecture="transformer")
        agent = AgentPassport(name="PRIVATE_AGENT", version="1.0", creator={"name": "Fixture"}, model_id=model.id, task_type="code-assistant", architecture="ReAct")
        registry.register_model(model)
        registry.register_agent(agent)

        def cli(*arguments, expected=0):
            result = subprocess.run([sys.executable, "-I", "-m", "forkit_radar.cli", *map(str, arguments)], cwd=project, env=environment, capture_output=True, text=True, timeout=45)
            assert result.returncode == expected, (arguments[:2], result.returncode, result.stderr)
            return result.stdout

        common = ["--store", store]
        assert '"state": "disabled"' in cli("metrics", "status", *common)
        assert not store.exists()
        checks.append("disabled_status_has_no_account_network_or_storage_creation")
        for index in range(2):
            start = json.loads(cli("session", "start", "--tool", "codex", "--registry", registry.root, "--passport-id", agent.id, "--json", *common))
            (project / "PRIVATE_file.py").write_text(f"value = {index}\n")
            cli("session", "stop", start["session_id"], *common)
        assert not (store / "reporting.sqlite3").exists()
        checks.append("local_receipts_work_without_reporting_profile")
        cli("metrics", "enable", "--endpoint", "http://127.0.0.1:8766/api/v1/radar", "--allow-local-collector", *common)
        models = root / "empty-models"
        models.mkdir()
        cli("scan", "--source", "models", "--models-root", models, "--no-save", "--metrics-store", store)
        model_input = root / "creation-input.json"
        model_input.write_text(json.dumps({"passport_type": "model", "name": "PRIVATE_CREATED_MODEL", "version": "1.0", "creator": {"name": "Fixture"}, "task_type": "text-generation", "architecture": "transformer"}))
        for index in range(2):
            cli("passport", "create", "--input", model_input, "--output", root / f"model-{index}.json", "--metrics-store", store)
        checks.append("enabled_local_operation_journal_records_scan_and_deduplicates_core_creation")
        target = output / "preview.json"
        cli("metrics", "preview", "--output", target, *common)
        packet = Preview.model_validate_json(target.read_bytes())
        w = packet.payload.weeks[-1]
        assert (w.receipts, w.meaningful_changes, w.reconstructable_changes, w.active_passports) == (2, 2, 2, 1)
        assert w.scans == w.successful_scans == w.passport_versions_created == 1
        assert packet.payload.latest_discovery.models == 0
        assert packet.payload.latest_discovery.agents is None
        checks.append("retained_receipt_counts_and_selected_passport_projection_match_ground_truth")
        checks.append("unselected_discovery_is_null_not_a_false_zero")
        before = hashlib.sha256(target.read_bytes()).hexdigest()
        cli("metrics", "preview", "--output", target, *common, expected=2)
        assert hashlib.sha256(target.read_bytes()).hexdigest() == before
        reporting = ReportingStore(store)
        with reporting._connect() as db:
            credential = reporting._profile(db)["credential"]
        for secret in (credential, agent.id, model.id, str(project), "PRIVATE_PROJECT", "PRIVATE_AGENT", "PRIVATE_MODEL", "PRIVATE_file.py"):
            assert secret.encode() not in target.read_bytes()
        assert target.stat().st_mode & 0o777 == 0o600
        checks.append("exact_preview_excludes_private_data_and_credential_and_refuses_overwrite")
        cli("metrics", "disable", *common)
        cli("metrics", "send", "--preview", target, "--sha256", before, *common, expected=2)
        assert len(json.loads(cli("history", "--json", *common))) == 2
        checks.append("disabled_send_is_refused_and_local_history_remains_available")
        assert reporting.status()["last_sent_sequence"] == 0
        checks.append("preview_never_publishes_or_claims_an_acknowledgement")
    result = {"status": "passed", "checks": checks, "python": platform.python_version(), "platform": platform.platform(),
              "limitations": ["Controlled local fixture, not user traction", "This installed workflow makes no network request; real HTTP/PostgreSQL integration is recorded separately"]}
    (output / "results.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"checks": len(checks), "status": "passed"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

