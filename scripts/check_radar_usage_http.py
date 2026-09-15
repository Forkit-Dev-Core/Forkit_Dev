"""Installed usage CLI/short-lived worker against an explicit loopback collector."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    url = urlsplit(args.endpoint)
    assert url.scheme == "http" and url.hostname == "127.0.0.1" and url.path == "/api/v1/radar"
    checks = []
    with tempfile.TemporaryDirectory(prefix="forkit-usage-http-") as temporary:
        root = Path(temporary).resolve()
        env = os.environ | {"FORKIT_USAGE_STORE": str(root / "usage"), "CI": "1"}
        project = root / "PRIVATE-project"
        project.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
        private = project / "SECRET-source.py"
        private.write_text("before\n")
        sessions = root / "sessions"

        def cli(*argv, expected=0):
            r = subprocess.run(
                [sys.executable, "-I", "-m", "forkit_radar.cli", *map(str, argv)],
                cwd=project,
                env=env,
                text=True,
                capture_output=True,
                timeout=20,
            )
            assert r.returncode == expected, (argv[:2], r.returncode, r.stderr)
            return r.stdout

        cli("start", "--tool", "cursor", "--store", sessions)
        private.write_text("after\n")
        original = json.loads(cli("stop", "--store", sessions, "--json"))
        assert json.loads(cli("usage", "status"))["state"] == "disabled"
        assert not (root / "usage").exists()
        checks.append("first_real_git_receipt_without_account_consent_or_reporting_state")
        flags = [
            "--endpoint",
            args.endpoint,
            "--consent",
            "usage-v2",
            "--store",
            sessions,
            "--validation",
            "--allow-local-collector",
        ]
        cli("usage", "enable", *flags)
        assert sum(d["receipts"] for d in json.loads(cli("usage", "preview"))["days"]) == 0
        assert json.loads(cli("usage", "status"))["last_sent_sequence"] == 0
        checks.append("new_consent_no_send_or_history_backfill")
        cli("usage", "enable", *flags, "--include-latest")
        assert sum(d["receipts"] for d in json.loads(cli("usage", "preview"))["days"]) == 1
        checks.append("explicit_latest_only_inclusion")
        try:
            cli(
                "session",
                "run",
                "--tool",
                "codex",
                "--store",
                sessions,
                "--",
                sys.executable,
                "-I",
                "-c",
                "from pathlib import Path; Path('SECRET-source.py').write_text('next change\\n')",
            )
            deadline = time.monotonic() + 10
            status = {}
            while time.monotonic() < deadline:
                status = json.loads(cli("usage", "status"))
                if status["last_result"] in {"confirmed", "unconfirmed"}:
                    break
                time.sleep(0.1)
            assert status["last_result"] == "confirmed", status
            assert status["last_sent_sequence"] == 1
            checks.append("installed_background_worker_exact_ack_from_real_http_postgresql")
            for _ in range(2):
                cli("receipt", "--store", sessions, "--json")
            p = json.loads(cli("usage", "preview"))
            assert sum(d["receipts"] for d in p["days"]) == 2
            raw = json.dumps(p)
            for secret in (str(project), private.name, original["session_id"], "next change"):
                assert secret not in raw
            checks.append("receipt_views_do_not_inflate_and_private_content_excluded")
            # Another selected project shares the one installation profile.
            second = root / "PRIVATE-second-project"
            second.mkdir()
            subprocess.run(["/usr/bin/git", "init", "-q", str(second)], check=True)
            cli("start", "--project", second, "--tool", "other", "--store", root / "second-store")
            cli("stop", "--project", second, "--store", root / "second-store")
            assert sum(d["receipts"] for d in json.loads(cli("usage", "preview"))["days"]) == 3
            assert json.loads(cli("usage", "status"))["last_sent_sequence"] == 1
            checks.append("multiple_projects_share_profile_and_24_hour_limit")
            cli("usage", "disable")
            assert json.loads(cli("usage", "status"))["state"] == "disabled"
            assert json.loads(cli("receipt", "--store", sessions, "--json"))
            checks.append("disable_preserves_local_results")
        finally:
            cli("usage", "withdraw")
        assert json.loads(cli("usage", "status"))["state"] == "withdrawn"
        checks.append("authenticated_withdrawal_confirmed")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(
            {
                "status": "passed",
                "checks": checks,
                "count": len(checks),
                "traffic": "synthetic local validation, never adoption",
            },
            indent=2,
        )
        + "\n"
    )
    print(f"{len(checks)} installed usage/HTTP checks passed")


if __name__ == "__main__":
    main()
