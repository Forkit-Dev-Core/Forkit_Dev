"""Capacity, safe compaction and private SQLite backup with real local databases."""

import json
import os
import sqlite3
import subprocess

import pytest

from forkit_radar.cli import main
from forkit_radar.identity.storage import MAX_STORE_BYTES
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.maintenance import backup, compact, recover, status
from forkit_radar.sessions.storage import SessionStore


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(root)], check=True)
    (root / "main.py").write_text("print('baseline')")
    return root


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "state")


def session(store, project):
    started, _ = store.start(project, tool="other")
    return store.finish(started.session_id)


def rows(store):
    with store._connect() as db:
        return db.execute("SELECT * FROM receipts ORDER BY ordinal").fetchall()


def test_capacity_write_rolls_back_without_stranding_history(store, project):
    receipt = session(store, project)
    original = rows(store)
    with pytest.raises(ContractError, match="store_capacity_exhausted"):
        with store._connect(write=True) as db:
            db.execute("INSERT INTO settings VALUES ('large', zeroblob(?))", (MAX_STORE_BYTES,))
    assert (store.root / "sessions.sqlite3").stat().st_size <= MAX_STORE_BYTES
    assert store.receipt() == receipt and rows(store) == original
    with store._connect() as db:
        assert db.execute("SELECT value FROM settings WHERE name='large'").fetchone() is None
    assert session(store, project).comparison == "complete"


def test_low_capacity_start_is_actionable_and_never_creates_session(store, project, capsys):
    first = session(store, project)
    with store._connect(write=True) as db:
        db.execute("INSERT INTO settings VALUES ('padding', zeroblob(?))", (61 * 1024 * 1024,))
    assert status(store)["state"] == "near_capacity"
    assert main(["session", "start", "--tool", "other", "--project", str(project), "--store", str(store.root)]) == 2
    assert "storage backup" in capsys.readouterr().err
    assert not store.active() and store.receipt() == first


def test_backup_preserves_canonical_receipts_and_active_baseline(store, project, tmp_path):
    session(store, project)
    started, _ = store.start(project, tool="cursor")
    destination = tmp_path / "restored"
    destination.mkdir(mode=0o700)
    original = rows(store)
    path = destination / "sessions.sqlite3"
    backup(store, path)
    assert path.stat().st_mode & 0o777 == 0o600
    restored = SessionStore(destination)
    assert rows(restored) == original
    assert restored.active()[0].started == started
    recovered = restored.finish(started.session_id, outcome="recovered")
    assert recovered.elapsed_ms is None and recovered.comparison == "partial"
    assert store.active()[0].started == started  # Backup is independent.
    assert rows(store) == original
    with pytest.raises(FileExistsError):
        backup(store, path)


def test_compact_is_preview_first_and_retains_all_receipts_active_and_recent_endpoints(store, project, tmp_path):
    other = tmp_path / "other"
    other.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(other)], check=True)
    receipts = [session(store, project) for _ in range(4)]
    other_receipt = session(store, other)
    active, _ = store.start(project, tool="cursor")
    original = rows(store)
    before = status(store)
    plan = compact(store, keep=2)
    assert not plan["applied"] and plan["snapshots"] == 7
    assert status(store) == before and rows(store) == original
    applied = compact(store, keep=2, apply=True)
    assert applied["snapshots"] == plan["snapshots"]
    assert rows(store) == original and len(store.history()) == 5
    with store._connect() as db:
        kept = set(db.execute("SELECT session_id, phase FROM snapshots"))
    assert kept == {(r.session_id, "after") for r in receipts[-2:] + [other_receipt]} | {(active.session_id, "before")}
    result = store.finish(active.session_id)
    assert result.since_previous.baseline_session_id == receipts[-1].session_id
    assert result.comparison == "complete"


def test_repeated_compaction_is_idempotent(store, project):
    session(store, project)
    compact(store, keep=1, apply=True)
    assert compact(store, keep=1, apply=True)["snapshots"] == 0


@pytest.mark.parametrize("keep", [0, 101, -1, True, 1.5, "20"])
def test_invalid_retention_cannot_mutate(store, project, keep):
    session(store, project)
    before = status(store)
    with pytest.raises(ContractError):
        compact(store, keep=keep, apply=True)
    assert status(store) == before


def test_status_never_initializes_empty_store(store, capsys):
    assert status(store)["state"] == "not_initialized"
    assert main(["storage", "status", "--store", str(store.root), "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["state"] == "not_initialized"
    assert not store.root.exists()


def test_cli_backup_and_compaction(store, project, tmp_path, capsys):
    session(store, project)
    destination = tmp_path / "backup.sqlite3"
    assert main(["storage", "backup", "--store", str(store.root), "--output", str(destination)]) == 0
    assert "keep it private" in capsys.readouterr().out
    assert main(["storage", "compact", "--store", str(store.root), "--keep", "1", "--json"]) == 0
    assert not json.loads(capsys.readouterr().out)["applied"]
    assert main(["storage", "compact", "--store", str(store.root), "--keep", "1", "--apply", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["applied"]


def test_backup_symlink_never_overwrites(store, project, tmp_path):
    session(store, project)
    target = tmp_path / "existing"
    target.write_text("unchanged")
    link = tmp_path / "link"
    link.symlink_to(target)
    with pytest.raises(FileExistsError):
        backup(store, link)
    assert target.read_text() == "unchanged"


def test_backup_detects_corrupt_store_without_publishing(store, project, tmp_path):
    session(store, project)
    database = store.root / "sessions.sqlite3"
    database.write_bytes(b"not sqlite")
    os.chmod(database, 0o600)
    destination = tmp_path / "backup"
    with pytest.raises(ContractError):
        backup(store, destination)
    assert not destination.exists()


def test_killed_transaction_recovers_without_losing_committed_receipts(store, project):
    receipt = session(store, project)
    original = rows(store)
    code = """import os, sqlite3, sys
db=sqlite3.connect(sys.argv[1]); db.execute('PRAGMA cache_size=10')
db.execute('BEGIN IMMEDIATE'); db.execute("INSERT INTO settings VALUES ('uncommitted', zeroblob(2000000))")
os._exit(9)
"""
    import sys

    result = subprocess.run([sys.executable, "-c", code, str(store.root / "sessions.sqlite3")])
    assert result.returncode == 9
    # Explicit recovery lets SQLite roll back its hot journal without creating
    # a session or inventing any new history.
    assert recover(store)["active_sessions"] == 0
    assert store.receipt(receipt.session_id) == receipt
    assert rows(store) == original
    with sqlite3.connect(store.root / "sessions.sqlite3") as db:
        assert db.execute("SELECT value FROM settings WHERE name='uncommitted'").fetchone() is None
