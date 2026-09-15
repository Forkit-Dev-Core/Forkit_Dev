"""Installed Prompt 7 workflow with real npm-generated locks and Core registry."""

from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    args = parser.parse_args()
    from forkit_radar.sessions.cli import render
    from forkit_radar.sessions.details import ReceiptV2, Selection
    from forkit_radar.sessions.storage import SessionStore

    from forkit.registry.local import LocalRegistry
    from forkit.schemas import AgentPassport, ModelPassport

    report = {
        "status": "running",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "checks": [],
        "network_attempts": 0,
    }
    secret = "NEVER_PERSIST_SESSION_DETAIL_554dc"

    def audit(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
            report["network_attempts"] += 1
            raise AssertionError("unexpected network access")

    sys.addaudithook(audit)
    with tempfile.TemporaryDirectory(prefix="radar-details-check-") as temp:
        root = Path(temp).resolve()
        project = root / "project"
        project.mkdir()
        subprocess.run(
            ["/usr/bin/git", "init", "-q", str(project)], check=True, capture_output=True
        )
        model = ModelPassport(
            name="local-model",
            version="1.0",
            creator={"name": "Fixture"},
            task_type="text-generation",
            architecture="transformer",
        )
        agent = AgentPassport(
            name="support-agent",
            version="1.0",
            creator={"name": "Fixture"},
            model_id=model.id,
            task_type="customer-support",
            architecture="ReAct",
        )
        registry = LocalRegistry(root / "registry")
        registry.register_model(model)
        registry.register_agent(agent)
        registry_before = {p: p.read_bytes() for p in registry.root.rglob("*") if p.is_file()}
        selected = Selection(registry=str(registry.root), passport_id=agent.id)
        store = SessionStore(root / "state")
        (project / "package.json").write_text(
            json.dumps({"dependencies": {"is-number": "6.0.0"}, "privateFixtureCredential": secret})
        )
        (project / "package-lock.json").write_bytes(
            (args.fixtures / "npm-is-number-6.0.0-lock.json").read_bytes()
        )
        (project / ".codex").mkdir()
        (project / ".codex/config.toml").write_text('model="model-a"\n')
        (project / ".env").write_text(secret)
        started, _ = store.start(project, tool="codex", selection=selected)
        (project / "package.json").write_text(json.dumps({"dependencies": {"is-number": "7.0.0"}}))
        (project / "package-lock.json").write_bytes(
            (args.fixtures / "npm-is-number-7.0.0-lock.json").read_bytes()
        )
        (project / ".codex/config.toml").write_text(
            'model="model-b"\n[mcp_servers.playwright]\ncommand="npx"\nargs=["@playwright/mcp", "'
            + secret
            + '"]\n'
        )
        (project / "new.ts").write_text("export const result = 42;\n")
        receipt = SessionStore(store.root).finish(started.session_id)
        assert {c.category for c in receipt.metadata.changes} == {"dependencies", "tools", "models"}
        locked = next(c for c in receipt.metadata.changes if c.source == "npm-lock")
        assert (locked.before, locked.after, locked.label) == ("6.0.0", "7.0.0", "is-number")
        assert (
            receipt.passport_id == agent.id
            and receipt.passport_after.model_reference == "consistent"
        )
        assert receipt.meaningful_categories == ("files", "dependencies", "tools", "models")
        report["checks"].extend(
            [
                "npm_generated_lock_version_change",
                "MCP_addition_and_configured_model_change",
                "explicit_raw_valid_core_association_without_account",
            ]
        )
        report["example_receipt"] = receipt.model_dump(mode="json")
        report["terminal_receipt"] = render(receipt)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.with_suffix(".txt").write_text(render(receipt) + "\n")
        (project / "between.py").write_text("between sessions\n")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "forkit_radar.cli",
                "session",
                "run",
                "--tool",
                "other",
                "--project",
                str(project),
                "--store",
                str(store.root),
                "--registry",
                str(registry.root),
                "--passport-id",
                agent.id,
                "--json",
                "--",
                sys.executable,
                "-c",
                "from pathlib import Path; Path('during.py').write_text('during session')",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        current = ReceiptV2.model_validate_json(result.stdout)
        assert {c.path for c in current.file_changes} == {"during.py"}
        assert {c.path for c in current.between_sessions.file_changes} == {"between.py"}
        assert current.since_previous.baseline_session_id == receipt.session_id
        report["checks"].append("installed_wrapper_distinguishes_during_from_between_sessions")
        started, _ = store.start(project, tool="other", selection=selected)
        (project / "package.json").write_text("malformed fixture")
        partial = store.finish(started.session_id)
        assert partial.dependency_comparison == "partial"
        assert not [c for c in partial.metadata.changes if c.kind == "removed"]
        (project / "package.json").write_text(json.dumps({"dependencies": {"is-number": "7.0.0"}}))
        started, _ = store.start(project, tool="other", selection=selected)
        last = store.finish(started.session_id)
        assert last.since_previous.baseline_session_id == current.session_id
        assert last.since_previous.skipped_sessions == 1
        assert not last.metadata.changes and not last.file_changes
        report["checks"].append("partial_reads_no_false_removals_previous_complete_baseline")
        assert len(store.history()) == 4 and not store.active()
        assert registry_before == {
            p: p.read_bytes() for p in registry.root.rglob("*") if p.is_file()
        }
        raw = (store.root / store.database_name).read_bytes()
        assert secret.encode() not in raw and b"export const result" not in raw
        assert (
            str(project) not in receipt.model_dump_json()
            and "locator_key" not in receipt.model_dump_json()
        )
        assert (store.root / store.database_name).stat().st_mode & 0o777 == 0o600
        report["checks"].append(
            "persistent_private_history_no_secrets_source_upload_or_registry_writes"
        )
    report["status"] = "passed"
    report["limitations"] = [
        "Declared configuration; no authenticated runtime, inferred lineage or AI authorship",
        "Project-layer metadata only, bounded supported formats",
        "No AI inference, GUI automation or non-macOS result implied",
        "Python audit hooks alone are not independent packet tracing",
    ]
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({k: report[k] for k in ("status", "checks", "network_attempts")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
