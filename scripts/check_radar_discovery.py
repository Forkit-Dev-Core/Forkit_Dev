"""Exercise installed discovery; retain only allowlisted validation metrics.

Python audit/native-method instrumentation is not a full OS packet trace.
Run in a fresh runtime environment for packaging evidence.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import statistics
import subprocess
import sys
from collections import Counter
from pathlib import Path

import psutil
from forkit_radar.discovery.collectors import applications, processes
from forkit_radar.discovery.mcp import codex, cursor
from forkit_radar.discovery.ollama import ollama
from forkit_radar.discovery.scan import scan
from forkit_radar.discovery.types import DEFAULT_DETECTORS, ScanReport


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-process-access", action="store_true")
    args = parser.parse_args()
    environment = {"platform": platform.platform(), "python": platform.python_version()}
    result = subprocess.run(
        [sys.executable, "-I", "-B", "-m", "forkit_radar.cli", "scan", "--no-save", "--json"],
        capture_output=True,
        timeout=20,
        cwd="/",
    )
    assert result.returncode in (0, 1) and result.stderr == b""
    report = ScanReport.model_validate(json.loads(result.stdout))
    assert report.storage == "not_saved" and report.continuity == "not_evaluated"
    assert len(report.sources) == 18
    assert all(s.status not in {"malformed", "timeout"} for s in report.sources)
    if args.require_process_access:
        process_source = next(s for s in report.sources if s.detector == "processes")
        assert process_source.status in {"complete", "partial"}
        assert process_source.reason in {"process_table_read", "process_visibility_limited"}
    for source in report.sources:
        for finding in source.findings:
            assert finding.evidence.association == "unmatched"
            assert finding.evidence.runtime == "not_observed"
            assert finding.evidence.passport == "unsupported"
            manifest = finding.observation.manifest
            if manifest is not None:
                assert manifest.logical_agent_id is None and manifest.passport_id is None

    attempts = {"network": 0, "non_radar_execution": 0, "native_cmdline_or_environ": 0}
    workers = []

    def audit(event, values):
        if event.startswith("socket."):
            attempts["network"] += 1
            raise RuntimeError("network_operation_forbidden")
        if event == "subprocess.Popen":
            command = values[1]
            expected = [sys.executable, "-I", "-B", "-m", "forkit_radar.discovery.worker"]
            if command[:-1] == expected and command[-1] in DEFAULT_DETECTORS:
                workers.append(command[-1])
                return
            attempts["non_radar_execution"] += 1
            raise RuntimeError("external_execution_forbidden")
        if event in {"os.system", "os.exec", "os.posix_spawn", "os.spawn"}:
            attempts["non_radar_execution"] += 1
            raise RuntimeError("external_execution_forbidden")

    def forbidden_native(_self):
        attempts["native_cmdline_or_environ"] += 1
        raise RuntimeError("command_or_environment_collection_forbidden")

    sys.addaudithook(audit)
    original_cmdline = psutil._psplatform.Process.cmdline
    original_environ = psutil._psplatform.Process.environ
    psutil._psplatform.Process.cmdline = forbidden_native
    psutil._psplatform.Process.environ = forbidden_native
    try:
        direct_apps = list(applications(Path.home()))
        direct_processes = list(processes())
        home = Path.home()
        direct_metadata = [
            *codex(home, codex_home=Path(os.environ.get("CODEX_HOME", str(home / ".codex")))),
            *cursor(home),
            *ollama(Path(os.environ.get("OLLAMA_MODELS", str(home / ".ollama/models")))),
        ]
    finally:
        psutil._psplatform.Process.cmdline = original_cmdline
        psutil._psplatform.Process.environ = original_environ
    samples = [scan().elapsed_ms for _ in range(3)]
    assert workers == list(DEFAULT_DETECTORS) * 3
    assert not any(attempts.values())
    evidence = {
        "step": "S05",
        "status": "passed",
        **environment,
        "psutil": psutil.__version__,
        "cli_exit": result.returncode,
        "cli_sources": len(report.sources),
        "source_statuses": dict(Counter(s.status for s in report.sources)),
        "candidate_observations": report.candidate_count,
        "scopes": [
            {
                "scope": s.scope,
                "status": s.status,
                "reason": s.reason,
                "candidate_observations": sum(
                    f.observation.manifest is not None for f in s.findings
                ),
            }
            for s in report.sources
        ],
        "scan_elapsed_ms": samples,
        "median_elapsed_ms": statistics.median(samples),
        "python_audit_and_native_api_attempts": attempts,
        "owned_worker_launches_observed": len(workers),
        "direct_collector_statuses": dict(
            Counter(r.status for r in direct_apps + direct_processes + direct_metadata)
        ),
        "limitations": [
            "One host; no representative discovery or association accuracy measurement",
            "Python audit hooks and blocked native metadata methods are not an OS packet/process trace",
            "No enrollment, continuity comparison, runtime authentication or persistent history exercised",
            "Recognized product metadata can be spoofed; it is only candidate evidence",
            "MCP entries are declarations with bounded source precedence, not server/tool/runtime authentication",
            "No Ollama blob or agent source is inspected; model descriptors remain declared",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(
        "Installed CLI, real metadata reads and bounded scans passed; no stronger identity claim."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
