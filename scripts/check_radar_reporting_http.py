"""Real installed Python client -> local Node collector -> disposable PostgreSQL."""
from __future__ import annotations

import argparse
import hashlib
import http.client
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from forkit_radar.discovery.scan import scan
from forkit_radar.reporting.storage import ReportingStore, note_scan
from forkit_radar.sessions.details import Selection
from forkit_radar.sessions.storage import SessionStore

from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    endpoint = urlsplit(args.endpoint)
    assert endpoint.scheme == "http" and endpoint.hostname == "127.0.0.1" and endpoint.path == "/api/v1/radar"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []

    def public():
        connection = http.client.HTTPConnection(endpoint.hostname, endpoint.port, timeout=8)
        try:
            connection.request("GET", endpoint.path + "/metrics")
            response = connection.getresponse()
            assert response.status == 200
            result = json.loads(response.read(16384))
            assert result["environment"] == "validation"
            return result
        finally:
            connection.close()

    with tempfile.TemporaryDirectory(prefix="forkit-reporting-http-") as temporary:
        root = Path(temporary).resolve()
        project = root / "PRIVATE_PROJECT"
        project.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
        (project / "langgraph.json").write_text('{"graphs":{"PRIVATE_graph":"./PRIVATE_agent.py:graph"}}')
        model = ModelPassport(name="PRIVATE_MODEL", version="1.0", creator={"name": "Fixture"}, task_type="text-generation", architecture="transformer")
        agent = AgentPassport(name="PRIVATE_AGENT", version="1.0", creator={"name": "Fixture"}, model_id=model.id, task_type="code-assistant", architecture="ReAct")
        registry = LocalRegistry(root / "registry")
        registry.register_model(model)
        registry.register_agent(agent)
        models_root = root / "ollama"
        manifest = models_root / "manifests/registry.ollama.ai/library/llama3.2/latest"
        manifest.parent.mkdir(parents=True)
        manifest.write_bytes((ROOT / "packages/radar/tests/fixtures/adapters/ollama-llama3.2-manifest.json").read_bytes())
        report = scan(("ollama", "langgraph"), project=project, models_root=models_root)
        assert report.candidate_count == 2
        selection = Selection(registry=str(registry.root), passport_id=agent.id)

        def cli(*arguments, expected=0):
            result = subprocess.run([sys.executable, "-I", "-m", "forkit_radar.cli", *map(str, arguments)], cwd=project, capture_output=True, text=True, timeout=45)
            assert result.returncode == expected, (arguments[:2], result.returncode, result.stderr)
            return result.stdout

        assert public()["status"] == "empty"
        for index in range(6):
            store_path = root / f"store-{index}"
            session_store = SessionStore(store_path)
            started, _ = session_store.start(project, tool="codex", selection=selection)
            (project / "PRIVATE_file.py").write_text(f"value = {index}\n")
            session_store.finish(started.session_id)
            cli("metrics", "enable", "--store", store_path, "--endpoint", args.endpoint, "--allow-local-collector")
            reporting = ReportingStore(store_path)
            note_scan(store_path, report)
            model_input = root / f"model-input-{index}.json"
            model_input.write_text(json.dumps({"passport_type": "model", "name": "PRIVATE_CREATED_MODEL", "version": f"{index + 2}.0", "creator": {"name": "Fixture"}, "task_type": "text-generation", "architecture": "transformer"}))
            cli("passport", "create", "--input", model_input, "--output", root / f"created-{index}.json", "--metrics-store", store_path)
            preview = output / f"preview-{index}.json"
            cli("metrics", "preview", "--store", store_path, "--output", preview)
            fingerprint = hashlib.sha256(preview.read_bytes()).hexdigest()
            cli("metrics", "send", "--store", store_path, "--preview", preview, "--sha256", "0" * 64, expected=2)
            cli("metrics", "send", "--store", store_path, "--preview", preview, "--sha256", fingerprint)
            cli("metrics", "send", "--store", store_path, "--preview", preview, "--sha256", fingerprint)
            assert reporting.status()["last_sent_sequence"] == 1
            with reporting._connect() as db:
                credential = reporting._profile(db)["credential"]
            assert credential not in preview.read_text()
            if index < 4:
                assert public()["status"] == "collecting"
        before = public()
        assert before["status"] == "available"
        assert before["metrics"]["reporting_profiles"] == 6
        assert before["metrics"]["receipts"] == before["metrics"]["meaningful_changes"] == 6
        assert before["metrics"]["latest_discovery"]["models"] == before["metrics"]["latest_discovery"]["agents"] == 6
        checks.extend(["installed_cli_exact_preview_and_sha256_publication", "wrong_preview_hash_never_contributes",
                       "identical_http_retries_leave_one_snapshot_per_profile", "real_ollama_and_langgraph_metadata_count_without_runtime_claim",
                       "small_cohort_suppression_before_five_profiles"])
        cli("metrics", "disable", "--store", store_path)
        cli("metrics", "send", "--store", store_path, "--preview", preview, "--sha256", fingerprint, expected=2)
        assert public()["metrics"]["reporting_profiles"] == 6
        cli("metrics", "withdraw", "--store", store_path)
        cli("metrics", "withdraw", "--store", store_path)
        assert len(session_store.history()) == 1
        result = public()
        m = result["metrics"]
        assert m["reporting_profiles"] == m["receipts"] == m["meaningful_changes"] == m["reconstructable_changes"] == m["weekly_active_passports"] == m["passport_versions_created"] == m["successful_scans"] == 5
        assert m["latest_discovery"]["models"] == m["latest_discovery"]["agents"] == 5
        assert m["latest_discovery"]["mcp_servers"] is None
        assert m["repeat_check_rate_basis_points"] == 0
        assert m["reconstructable_change_rate_basis_points"] == 10000
        assert m["total_installs"] is None
        assert "PRIVATE" not in json.dumps(result) and agent.id not in json.dumps(result)
        checks.extend(["disable_keeps_existing_contribution_until_explicit_withdrawal", "authenticated_withdrawal_is_idempotent_and_preserves_local_history",
                       "public_counts_and_denominators_match_five_retained_fixture_profiles", "server_output_excludes_core_ids_names_paths_and_credentials"])
        (output / "public-metrics.json").write_text(json.dumps(result, indent=2) + "\n")
    record = {"status": "passed", "checks": checks, "platform": platform.platform(), "python": platform.python_version(),
              "fixture_profiles_submitted": 6, "fixture_profiles_withdrawn": 1, "fixture_profiles_remaining": 5,
              "limitations": ["Controlled local fixtures; these are not users, installs, beta validation or traction", "Metadata declarations and unsigned local history, not authenticated AI execution"]}
    (output / "results.json").write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"checks": len(checks), "status": "passed", "fixture_profiles": 5}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
