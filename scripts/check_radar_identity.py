"""Real local Core registry and persistent drafts in an installed runtime only."""

from __future__ import annotations

import argparse
import json
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path

from forkit_radar.discovery.scan import scan
from forkit_radar.identity.enrollment import preview, select_source
from forkit_radar.identity.passports import check_bytes, create_bytes, lookup
from forkit_radar.identity.storage import EnrollmentStore, write_new

from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture", type=Path, required=True)
    args = parser.parse_args()
    fixture = json.loads(args.fixture.read_bytes())
    attempts = {"network": 0, "non_radar_execution": 0}

    def audit(event, values):
        if event.startswith("socket."):
            attempts["network"] += 1
            raise RuntimeError("network_forbidden")
        if event == "subprocess.Popen":
            command = values[1]
            if command[:5] == [sys.executable, "-I", "-B", "-m", "forkit_radar.discovery.worker"]:
                return
            if command[:4] == [sys.executable, "-I", "-m", "forkit_radar.cli"]:
                return
            attempts["non_radar_execution"] += 1
            raise RuntimeError("execution_forbidden")
        if event in {"os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
            attempts["non_radar_execution"] += 1
            raise RuntimeError("execution_forbidden")

    sys.addaudithook(audit)
    with tempfile.TemporaryDirectory(prefix="radar-identity-") as temp:
        root = Path(temp).resolve()
        model_input = {
            "passport_type": "model",
            "name": "test-model",
            "version": "1.0.0",
            "creator": {"name": "Test operator"},
            "task_type": "text-generation",
            "architecture": "transformer",
        }
        model = ModelPassport.from_dict(json.loads(create_bytes(json.dumps(model_input).encode())))
        agent = AgentPassport(
            name="support-agent",
            version="1.0.0",
            creator={"name": "Test operator"},
            model_id=model.id,
            task_type="customer-support",
            architecture="ReAct",
        )
        registry = LocalRegistry(root / "core-registry")
        registry.register_model(model)
        registry.register_agent(agent)
        assert lookup(registry.root, agent.id, "agent").status == "consistent"
        broken = agent.to_dict()
        broken.pop("id")
        assert check_bytes(json.dumps(broken).encode()).status == "invalid"
        fixture["passport_id"] = agent.id
        path = root / "agent.json"
        path.write_text(json.dumps(fixture))
        report = scan(("agent-manifest",), agent_file=path, registry=registry.root)
        evidence = report.sources[0].findings[0].evidence
        assert evidence.passport == "consistent" and evidence.association == "declared"
        assert evidence.runtime == "not_observed" and evidence.acceptance == "unreviewed"
        locator, manifest = select_source(agent_file=path)
        draft = EnrollmentStore(root / "private").propose(
            locator, preview(manifest, registry=registry.root)
        )
        restarted = EnrollmentStore(root / "private")
        assert restarted.get(draft.draft.proposal_id) == draft
        assert restarted.cancel(draft.draft.proposal_id).state == "cancelled"
        clone = root / "clone.json"
        clone.write_bytes(path.read_bytes())
        locator2, manifest2 = select_source(agent_file=clone)
        second = restarted.propose(locator2, preview(manifest2, registry=registry.root))
        assert draft.draft.reserved_logical_agent_id != second.draft.reserved_logical_agent_id
        assert second.draft.authority_id is None and second.draft.accepted_binding_digest is None
        output = root / "created-model.json"
        write_new(output, create_bytes(json.dumps(model_input).encode()))
        cli = subprocess.run(
            [
                sys.executable,
                "-I",
                "-m",
                "forkit_radar.cli",
                "passport",
                "inspect",
                "--file",
                str(output),
            ],
            capture_output=True,
            cwd="/",
            timeout=8,
        )
        assert cli.returncode == 0 and cli.stderr == b""
        assert not any(attempts.values())
    args.output.write_text(
        json.dumps(
            {
                "step": "S05",
                "status": "passed",
                "sqlite": sqlite3.sqlite_version,
                "checks": [
                    "actual Core registration and raw lookup",
                    "missing ID rejected before repair",
                    "installed scan consistency stays declared",
                    "private draft persists across reopen",
                    "cancel retains original draft",
                    "cloned source reserves a distinct ID",
                    "no accepted authority/binding",
                    "exclusive Core document creation and installed CLI",
                ],
                "python_audit_attempts": attempts,
                "limits": [
                    "Controlled local data only",
                    "No authority/signature or authenticated runtime",
                    "No full history/backup/rollback assurance",
                    "API guards are not an independent OS packet trace",
                ],
            },
            indent=2,
        )
        + "\n"
    )
    print("Installed Core association and persistent pending-enrollment checks passed.")


if __name__ == "__main__":
    main()
