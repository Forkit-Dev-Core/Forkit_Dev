"""Installed-wheel release exercise: repeated real Git sessions and private maintenance."""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import statistics
import subprocess
import tempfile
import time
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    from forkit_radar.sessions.maintenance import backup, compact, status
    from forkit_radar.sessions.storage import SessionStore

    report = {"platform": platform.platform(), "python": platform.python_version(),
              "sessions": 24, "source_files": 1000, "checks": []}
    starts, stops = [], []
    with tempfile.TemporaryDirectory(prefix="forkit-release-") as temporary:
        root = Path(temporary).resolve()
        project = root / "project"
        project.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
        for index in range(1000):
            (project / f"file{index}.py").write_text(f"value = {index}\n")
        store = SessionStore(root / "private")
        previous = None
        for index in range(report["sessions"]):
            started_at = time.monotonic()
            started, snapshot = store.start(project, tool="other")
            starts.append(time.monotonic() - started_at)
            assert len(snapshot.files) == 1000
            (project / "file0.py").write_text(f"iteration = {index}\n")
            (project / f"file{index + 1}.py").unlink()
            (project / f"added{index}.py").write_text(f"added_iteration = {index}\n")
            stopped_at = time.monotonic()
            receipt = store.finish(started.session_id)
            stops.append(time.monotonic() - stopped_at)
            assert receipt.comparison == "complete"
            assert {(change.kind, change.path) for change in receipt.file_changes} == {
                ("modified", "file0.py"), ("removed", f"file{index + 1}.py"),
                ("added", f"added{index}.py"),
            }
            assert receipt.previous_session_id == previous
            if previous:
                assert receipt.since_previous.baseline_session_id == previous
            previous = receipt.session_id
        report["checks"].append("24_sessions_1000_files_exact_72_expected_change_events")

        def receipt_hashes(selected):
            with selected._connect() as db:
                return [hashlib.sha256(row[0]).hexdigest() for row in
                        db.execute("SELECT payload FROM receipts ORDER BY ordinal")]

        original = receipt_hashes(store)
        active, _ = store.start(project, tool="other")
        before = status(store)
        restored_dir = root / "restored"
        restored_dir.mkdir(mode=0o700)
        backup(store, restored_dir / "sessions.sqlite3")
        restored = SessionStore(restored_dir)
        assert receipt_hashes(restored) == original
        assert restored.active()[0].started == active
        preview = compact(store, keep=2)
        assert status(store) == before
        applied = compact(store, keep=2, apply=True)
        after = status(store)
        assert applied["snapshots"] == preview["snapshots"] == 46
        assert after["available_bytes"] > before["available_bytes"]
        assert receipt_hashes(store) == original
        final = store.finish(active.session_id)
        assert final.since_previous.baseline_session_id == previous
        assert not final.file_changes and not store.active()
        assert receipt_hashes(store)[:-1] == original
        assert len(store.history(limit=100)) == 25
        report["checks"].append("consistent_backup_preview_compaction_preserve_all_receipts_and_active_baseline")
        report["storage_before"] = before
        report["storage_after_compaction"] = after
        report["reclaimed_bytes"] = after["available_bytes"] - before["available_bytes"]
    report["capture_seconds"] = {
        phase: {"median": round(statistics.median(values), 4), "max": round(max(values), 4)}
        for phase, values in (("start", starts), ("stop", stops))
    }
    report["status"] = "passed"
    report["limitations"] = ["Controlled local Git workload, not AI authorship or universal accuracy evidence",
                             "Timings describe this host/workload only; not a long-term retention guarantee"]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
