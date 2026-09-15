"""Explicit local maintenance; retain every receipt and all active baselines."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import time
from pathlib import Path

from ..identity.storage import MAX_STORE_BYTES, write_new
from ..jsonio import ContractError

# Only finalized sessions with a retained receipt are eligible. Pruning before
# snapshots cannot affect an active session. Retain N latest after snapshots per
# project; older receipt JSON is never rewritten even when its snapshots expire.
ELIGIBLE = """SELECT sessions.session_id FROM sessions JOIN receipts USING(session_id)
WHERE sessions.state IN ('completed','interrupted')"""
RETAIN = """SELECT session_id FROM (
SELECT sessions.session_id, ROW_NUMBER() OVER (
PARTITION BY sessions.project_id ORDER BY receipts.ordinal DESC) AS position
FROM sessions JOIN receipts USING(session_id)
WHERE sessions.state IN ('completed','interrupted')) WHERE position <= ?"""
PRUNABLE = f"""session_id IN ({ELIGIBLE}) AND
(phase='before' OR (phase='after' AND session_id NOT IN ({RETAIN})))"""


def status(store):
    try:
        with store._connect() as db:
            size = db.execute("PRAGMA page_size").fetchone()[0]
            pages = db.execute("PRAGMA page_count").fetchone()[0]
            free = db.execute("PRAGMA freelist_count").fetchone()[0]
            used = (pages - free) * size
            return {
                "schema_version": "1.0", "state": "near_capacity" if MAX_STORE_BYTES - used < 8_388_608 else "ready",
                "database_bytes": pages * size, "used_bytes": used,
                "available_bytes": MAX_STORE_BYTES - used, "limit_bytes": MAX_STORE_BYTES,
                "receipt_count": db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0],
                "active_sessions": db.execute("SELECT COUNT(*) FROM sessions WHERE state='active'").fetchone()[0],
                "snapshot_count": db.execute("SELECT COUNT(*) FROM snapshots").fetchone()[0],
            }
    except FileNotFoundError:
        return {"schema_version": "1.0", "state": "not_initialized", "limit_bytes": MAX_STORE_BYTES}


def compact(store, *, keep: int = 20, apply: bool = False):
    if type(keep) is not int or not 1 <= keep <= 100 or type(apply) is not bool:
        raise ContractError("invalid_snapshot_retention")
    with store._connect(write=apply) as db:
        count, raw_bytes = db.execute(
            f"SELECT COUNT(*), COALESCE(SUM(LENGTH(payload)),0) FROM snapshots WHERE {PRUNABLE}", (keep,)
        ).fetchone()
        if apply:
            db.execute(f"DELETE FROM snapshots WHERE {PRUNABLE}", (keep,))
        return {
            "schema_version": "1.0", "applied": apply, "snapshots": count,
            "payload_bytes": raw_bytes, "keep_latest_after_snapshots_per_project": keep,
            "receipts_deleted": 0, "active_baselines_deleted": 0,
            "comparison_effect": "Older capture snapshots become unavailable for future baseline selection; saved receipts and all retained evolution revisions/links remain unchanged.",
            "space_effect": "Freed SQLite pages are reused by later sessions; file size may stay unchanged.",
        }


def recover(store):
    # SQLite replays a valid hot rollback journal while opening a writer. This
    # does not repair corrupt payloads or invent a session end boundary.
    with store._connect(write=True) as db:
        store._key(db)
        return {"recovery": "sqlite_check_complete", "active_sessions": db.execute(
            "SELECT COUNT(*) FROM sessions WHERE state='active'"
        ).fetchone()[0]}


def backup(store, output: Path):
    # Backup API reads a consistent SQLite snapshot, including active sessions.
    # A private temporary destination keeps partial backups out of the selected
    # output path. write_new is the same exclusive 0600 output boundary as cards.
    with tempfile.TemporaryDirectory(prefix="forkit-private-backup-") as temporary:
        path = Path(temporary) / "sessions.sqlite3"
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        os.close(descriptor)
        with store._connect() as source:
            target = sqlite3.connect(path)
            deadline = time.monotonic() + 10

            def progress(_status, _remaining, _total):
                if time.monotonic() > deadline:
                    raise ContractError("session_backup_timeout")

            try:
                source.backup(target, pages=128, progress=progress, sleep=0.05)
            except sqlite3.Error:
                raise ContractError("session_backup_unavailable") from None
            finally:
                target.close()
        with path.open("rb") as handle:
            raw = handle.read(MAX_STORE_BYTES + 1)
        if len(raw) > MAX_STORE_BYTES:
            raise ContractError("session_backup_limit")
        write_new(output, raw)
