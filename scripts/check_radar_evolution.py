"""Installed-wheel local evolution workflow and reproducible private preview.

Uses disposable Git projects, genuine Core registry records and explicit session
boundaries. It makes no inference call and claims no AI authorship.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from forkit_radar.identity.storage import canonical
from forkit_radar.sessions.details import Selection
from forkit_radar.sessions.maintenance import compact
from forkit_radar.sessions.storage import SessionStore
from forkit_radar.sessions.summary import build

from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--sessions", type=int, default=12)
    parser.add_argument("--files", type=int, default=250)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks = []
    environment = os.environ.copy()
    environment.pop("PYTHONPATH", None)
    with tempfile.TemporaryDirectory(prefix="forkit-evolution-check-") as directory:
        root = Path(directory).resolve()
        project = root / "project"
        project.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True, capture_output=True)
        for index in range(args.files):
            (project / f"module_{index}.py").write_text(f"value = {index}\n")
        registry_path = root / "registry"
        registry = LocalRegistry(registry_path)
        model = ModelPassport(name="fixture-model", version="1.0", creator={"name": "Local validation fixture"}, task_type="text-generation", architecture="transformer")
        agent = AgentPassport(name="Example support agent", version="1.0", creator={"name": "Local validation fixture"}, model_id=model.id, task_type="customer-support", architecture="ReAct")
        registry.register_model(model)
        registry.register_agent(agent)
        selected = Selection(registry=str(registry_path), passport_id=agent.id)
        store = SessionStore(root / "store")
        # Two known semantic events, despite two dependency file observations.
        first, _ = store.start(project, tool="codex", selection=selected)
        (project / "package.json").write_text(json.dumps({"dependencies": {"stripe": "^1.0.0"}}))
        (project / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"node_modules/stripe": {"version": "1.0.0"}}}))
        (project / "module_0.py").write_text("value = 100\n")
        store.finish(first.session_id)
        # One event with unknown session attribution, observed at next capture.
        (project / "between.py").write_text("value = 2\n")
        second, _ = store.start(project, tool="cursor", selection=selected)
        (project / ".mcp.json").write_text(json.dumps({"mcpServers": {"playwright": {"command": "NEVER_EXECUTE", "args": ["DO_NOT_RETAIN_SECRET_18a7"]}}}))
        (project / ".codex").mkdir()
        (project / ".codex/config.toml").write_text('model = "configured-model-example"\n')
        (project / "module_1.py").write_text("value = 200\n")
        store.finish(second.session_id)
        for index in range(args.sessions - 3):
            started, _ = store.start(project, tool="codex", selection=selected)
            (project / "module_2.py").write_text(f"value = {300 + index}\n")
            store.finish(started.session_id)
        last, _ = store.start(project, tool="claude-code", selection=selected)
        (project / "module_3.py").write_text("value = 400\n")
        (project / "package.json").write_text(json.dumps({"dependencies": {"stripe": "^2.0.0", "playwright": "^1.58.0"}}))
        (project / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"node_modules/stripe": {"version": "2.0.0"}, "node_modules/playwright": {"version": "1.58.0"}}}))
        (project / ".codex/config.toml").write_text('model = "configured-model-next"\n')
        store.finish(last.session_id)
        start = time.monotonic()
        result = build(store, timezone_name="UTC", limit=1)
        elapsed = time.monotonic() - start
        stats = result["periods"]["history"]
        assert result["total_receipts"] == args.sessions
        assert stats["meaningful_changes"] == args.sessions + 7, stats
        assert stats["reconstructable_changes"] == args.sessions + 6, stats
        assert stats["between_session_changes"] == 1
        assert stats["categories"]["dependencies"] == 3
        assert stats["categories"]["models"] == 2
        checks.append("deduplicated_dependency_file_and_lock_events_exact_counts")
        checks.append("gap_events_in_denominator_without_invented_session_attribution")
        checks.append("calendar_totals_include_all_receipts_beyond_display_limit")
        before = {r.session_id: canonical(r) for r in store.history(limit=100)}
        compact(store, keep=1, apply=True)
        after = build(store, timezone_name="UTC", limit=1)
        assert after["periods"] == result["periods"]
        assert {r.session_id: canonical(r) for r in store.history(limit=100)} == before
        checks.append("compaction_retains_every_revision_trace_and_receipt")
        def cli(*argv, expected=0):
            command = [sys.executable, "-m", "forkit_radar.cli", *argv, "--store", str(store.root)]
            process = subprocess.run(command, cwd=root, env=environment, capture_output=True, text=True, timeout=60)
            assert process.returncode == expected, (argv, process.returncode, process.stdout, process.stderr)
            return process
        for name in ("view", "summary"):
            process = cli(name, "--json", "--timezone", "UTC")
            parsed = json.loads(process.stdout)
            assert parsed["total_receipts"] == args.sessions
            assert parsed["periods"]["history"]["meaningful_changes"] == args.sessions + 7
        cli("view", "--output", str(output / "private-view.html"), "--timezone", "UTC")
        original_hash = hashlib.sha256((output / "private-view.html").read_bytes()).hexdigest()
        cli("view", "--output", str(output / "private-view.html"), expected=2)
        assert hashlib.sha256((output / "private-view.html").read_bytes()).hexdigest() == original_hash
        checks.append("installed_private_view_json_and_exclusive_file_output")
        for extension in ("html", "svg", "json"):
            target = output / f"weekly-card.{extension}"
            cli("summary-card", "--output", str(target), "--timezone", "UTC")
            for secret in (str(project), agent.id, "Example support agent", "DO_NOT_RETAIN_SECRET_18a7", "module_0.py"):
                assert secret.encode() not in target.read_bytes()
        checks.append("installed_separate_aggregate_cards_exclude_private_fields")
        cli("summary", "--timezone", "../invalid", expected=2)
        # Retained evidence checks no longer depend on live project/registry files.
        import shutil
        shutil.rmtree(project)
        shutil.rmtree(registry_path)
        assert build(store)["periods"]["history"] == stats
        checks.append("reconstruction_works_after_project_and_registry_are_unavailable")
        with sqlite3.connect(store.root / store.database_name) as db:
            db.execute("UPDATE observed_revisions SET payload=?", (b"corrupted",))
        broken = build(store)
        assert broken["periods"]["history"]["reconstructable_changes"] == 0
        cli("view", "--output", str(output / "broken-history.html"))
        checks.append("broken_retained_evidence_has_zero_reconstructable_claims")
    empty = SessionStore(output / "not-created")
    subprocess.run([sys.executable, "-m", "forkit_radar.cli", "view", "--store", str(empty.root), "--output", str(output / "empty-view.html")], cwd=output, env=environment, check=True, capture_output=True)
    assert not empty.root.exists()
    report = {
        "checks": checks + ["empty_view_does_not_create_store"], "platform": platform.platform(),
        "python": platform.python_version(), "fixture_sessions": args.sessions,
        "fixture_source_files": args.files, "summary_seconds": round(elapsed, 4),
        "expected_aggregate": stats,
        "limitations": ["Controlled Git/Core fixture; no live AI inference or authorship proof", "Unsigned local record integrity, not external attestation", "Preview contains example data, not user traction"],
    }
    (output / "results.json").write_text(json.dumps(report, indent=2))
    print(json.dumps({"checks": len(report["checks"]), "sessions": args.sessions, "summary_seconds": report["summary_seconds"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

