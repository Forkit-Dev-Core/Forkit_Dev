"""Exercise installed account-free receipts with real Git and local child processes."""

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
    parser.add_argument(
        "--coding-tool",
        type=Path,
        help="Optional explicit installed Codex binary, version probe only",
    )
    args = parser.parse_args()
    from forkit_radar.sessions.cli import render
    from forkit_radar.sessions.details import ReceiptV2 as Receipt
    from forkit_radar.sessions.storage import SessionStore

    report = {
        "status": "running",
        "platform": platform.platform(),
        "python": platform.python_version(),
        "checks": [],
        "network_attempts": 0,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    secret = "DO_NOT_PERSIST_SESSION_FIXTURE_6fa32"
    with tempfile.TemporaryDirectory(prefix="radar-session-check-") as temp:
        root = Path(temp).resolve()
        project = root / "project"
        project.mkdir()
        subprocess.run(
            ["/usr/bin/git", "init", "-q", str(project)], check=True, capture_output=True
        )
        (project / "main.py").write_text("existing dirty source\n")
        (project / ".env").write_text(secret)
        (project / "AGENTS.md").write_text(secret)
        (project / "credentials.py").write_text(secret)
        private = root / "private"
        store = SessionStore(private)

        def audit(event, _arguments):
            if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
                report["network_attempts"] += 1
                raise AssertionError("Session Receipt attempted network access")

        sys.addaudithook(audit)
        started, baseline = store.start(project, tool="codex")
        assert len(baseline.files) == 1
        (project / "new.ts").write_text("export const value = 42;\n")
        receipt = SessionStore(private).finish(started.session_id)
        assert [(c.kind, c.path) for c in receipt.file_changes] == [("added", "new.ts")]
        assert receipt.elapsed_ms is not None and store.receipt() == receipt
        report["checks"].append("manual_start_dirty_baseline_finish_restart_history")
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
                str(private),
                "--json",
                "--",
                sys.executable,
                "-c",
                "from pathlib import Path; Path('main.py').write_text('edited by explicit child'); print('uncaptured child output')",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=20,
        )
        child_receipt = Receipt.model_validate_json(result.stdout)
        assert child_receipt.file_changes[0].path == "main.py"
        assert child_receipt.previous_session_id == receipt.session_id
        assert "uncaptured child output" in result.stderr
        report["checks"].append("explicit_child_process_file_change_clean_json")
        report["example_receipt"] = child_receipt.model_dump(mode="json")
        report["terminal_receipt"] = render(child_receipt, files=True)
        if args.coding_tool:
            tool_result = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "forkit_radar.cli",
                    "session",
                    "run",
                    "--tool",
                    "codex",
                    "--project",
                    str(project),
                    "--store",
                    str(private),
                    "--json",
                    "--",
                    str(args.coding_tool),
                    "--version",
                ],
                check=True,
                capture_output=True,
                text=True,
                timeout=20,
            )
            tool_receipt = Receipt.model_validate_json(tool_result.stdout)
            assert tool_receipt.outcome == "command_exited" and not tool_receipt.file_changes
            report["coding_tool"] = {
                "kind": "codex",
                "probe": "version_only_no_AI_inference",
                "version_output": tool_result.stderr.strip(),
                "receipt_saved": True,
            }
            report["checks"].append("actual_installed_codex_wrapper_version_probe")
        for path in private.iterdir():
            contents = path.read_bytes()
            assert secret.encode() not in contents
            assert b"edited by explicit child" not in contents
            assert b"uncaptured child output" not in contents
            assert path.stat().st_mode & 0o777 == 0o600
        assert private.stat().st_mode & 0o777 == 0o700
        assert str(project) not in child_receipt.model_dump_json()
        assert "fingerprint" not in child_receipt.model_dump_json()
        report["checks"].append("local_only_private_storage_no_source_secrets_argv_or_output")
        report["session_count"] = len(store.history())
        assert not store.active()
    report["status"] = "passed"
    report["limitations"] = [
        "Tool selection is declared, not authenticated authorship",
        "No real AI inference session or GUI automation exercised",
        "OS matrix and independent packet tracing are separate checks",
        "Cloud is not implemented; semantic details and local share cards have separate installed workflows",
    ]
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(
        json.dumps(
            {
                "status": report["status"],
                "checks": report["checks"],
                "network_attempts": report["network_attempts"],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
