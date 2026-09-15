"""Real Git/Core/SQLite evidence, tampering and account-free private summaries."""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
import subprocess
import zlib
from datetime import datetime, timezone
from unittest.mock import patch

import pytest
from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport

from forkit_radar.identity.storage import canonical
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.details import DetailedSnapshot, Selection
from forkit_radar.sessions.evolution import SCHEMA, digest, normalized, unpack, verify
from forkit_radar.sessions.maintenance import backup, compact
from forkit_radar.sessions.private_view import render
from forkit_radar.sessions.storage import SessionStore, read_snapshot
from forkit_radar.sessions.summary import build, zone
from forkit_radar.sessions.summary_cards import SummaryCard, encode
from forkit_radar.sessions.summary_cards import project as card


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True, capture_output=True)
    (project / "main.py").write_text("print('before')\n")
    registry_path = tmp_path / "registry"
    registry = LocalRegistry(registry_path)
    model = ModelPassport(name="fixture-model", version="1.0", creator={"name": "Fixture"}, task_type="text-generation", architecture="transformer")
    agent = AgentPassport(name="support-agent", version="1.0", creator={"name": "Fixture"}, model_id=model.id, task_type="customer-support", architecture="ReAct")
    registry.register_model(model)
    registry.register_agent(agent)
    return project, SessionStore(tmp_path / "private"), Selection(registry=str(registry_path), passport_id=agent.id), registry, model, agent


def capture(setup, *, selection=True, edit=True, tool="codex", outcome="manual_stop"):
    project, store, selected, *_ = setup
    start, _ = store.start(project, tool=tool, selection=selected if selection else None)
    if edit:
        with (project / "main.py").open("a") as handle:
            handle.write("print('change')\n")
    return store.finish(start.session_id, outcome=outcome)


def sql(store):
    return sqlite3.connect(store.root / store.database_name)


def report(store):
    return build(store, timezone_name="UTC")


def test_trace_survives_compaction_and_backup(setup, tmp_path):
    project, store, *_ = setup
    first = capture(setup)
    (project / "gap.py").write_text("x = 1\n")
    second = capture(setup)
    expected = report(store)
    stats = expected["periods"]["history"]
    assert (stats["meaningful_changes"], stats["reconstructable_changes"], stats["between_session_changes"]) == (3, 2, 1)
    assert stats["reconstructable_change_rate"] == 6666
    assert all(r["trace"] == "complete" for r in expected["records"])
    assert expected["records"][0]["evolution"]["previous_session_id"] == first.session_id
    original = {r.session_id: canonical(r) for r in store.history()}
    compact(store, keep=1, apply=True)
    actual = report(store)
    assert actual["periods"] == expected["periods"]
    assert actual["records"] == expected["records"]
    assert {r.session_id: canonical(r) for r in store.history()} == original
    destination = tmp_path / "backup.sqlite3"
    backup(store, destination)
    restored = tmp_path / "restored"
    restored.mkdir(mode=0o700)
    shutil.copyfile(destination, restored / "sessions.sqlite3")
    (restored / "sessions.sqlite3").chmod(0o600)
    assert report(SessionStore(restored))["records"] == actual["records"]
    assert store.receipt(second.session_id).passport_id == setup[-1].id


def test_unchanged_and_reversion_keep_digest_but_append_events(setup):
    project, store, *_ = setup
    original = (project / "main.py").read_text()
    capture(setup, edit=False)
    first = report(store)["records"][0]
    assert first["evolution"]["before_revision"] == first["evolution"]["after_revision"]
    capture(setup)
    start, _ = store.start(project, tool="cursor", selection=setup[2])
    (project / "main.py").write_text(original)
    store.finish(start.session_id)
    rows = report(store)["records"]
    assert rows[0]["evolution"]["after_revision"] == first["evolution"]["before_revision"]
    assert [r["evolution"]["event_sequence"] for r in rows] == [3, 2, 1]


def test_normalization_ignores_order_diagnostics_and_exclusions(setup):
    project, store, *_ = setup
    start, _ = store.start(project, tool="codex", selection=setup[2])
    with sql(store) as db:
        raw = db.execute("SELECT payload FROM snapshots WHERE session_id=?", (start.session_id,)).fetchone()[0]
    _, snapshot = read_snapshot(raw)
    data = snapshot.model_dump(mode="json")
    data["files"]["excluded_count"] += 9
    data["files"]["reasons"] = ["different_diagnostic"]
    data["metadata"]["sources"].reverse()
    for source in data["metadata"]["sources"]:
        source["facts"].reverse()
        source["reason"] = "different_diagnostic"
    assert normalized(DetailedSnapshot.model_validate(data)) == normalized(snapshot)
    data["files"]["inventory_complete"] = False
    assert normalized(DetailedSnapshot.model_validate(data)) != normalized(snapshot)


def test_core_version_change_remains_declared_project_history(setup):
    project, store, selection, registry, model, first_agent = setup
    capture(setup)
    next_agent = AgentPassport(name=first_agent.name, version="2.0", creator={"name": "Fixture"}, model_id=model.id, task_type="customer-support", architecture="ReAct")
    registry.register_agent(next_agent)
    next_selection = Selection(registry=selection.registry, passport_id=next_agent.id)
    start, _ = store.start(project, tool="claude-code", selection=next_selection)
    (project / "main.py").write_text("print('new version')\n")
    receipt = store.finish(start.session_id)
    result = report(store)
    row = result["records"][0]
    assert receipt.passport_id == next_agent.id != first_agent.id
    assert row["trace"] == "complete"
    assert row["evolution"]["event_sequence"] == 2
    assert row["evolution"]["basis"] == "unsigned_local_project_history_declared_passport_associations"
    assert any(c["category"] == "passport" for c in row["between_changes"])
    assert "Agent continuity is unproven" in render(result).decode()


def test_model_config_revision_does_not_change_core_id(setup):
    project, store, *_ = setup
    config = project / ".codex/config.toml"
    config.parent.mkdir()
    config.write_text('model = "model-a"\n')
    start, _ = store.start(project, tool="codex", selection=setup[2])
    config.write_text('model = "model-b"\n')
    receipt = store.finish(start.session_id)
    row = report(store)["records"][0]
    assert receipt.passport_before.passport_id == receipt.passport_after.passport_id == setup[-1].id
    assert row["evolution"]["before_revision"] != row["evolution"]["after_revision"]
    assert len(row["changes"]) == 1 and row["changes"][0]["category"] == "models"
    assert row["reconstructable_changes"] == 1


def test_copied_project_same_passport_does_not_merge(setup, tmp_path):
    project, store, selection, *_ = setup
    first = capture(setup)
    clone = tmp_path / "clone"
    shutil.copytree(project, clone)
    start, _ = store.start(clone, tool="codex", selection=selection)
    (clone / "main.py").write_text("print('fork')\n")
    other = store.finish(start.session_id)
    assert other.project_id != first.project_id and other.passport_id == first.passport_id
    rows = report(store)["records"]
    assert all(r["evolution"]["event_sequence"] == 1 for r in rows)
    assert all(r["evolution"]["previous_session_id"] is None for r in rows)
    assert build(store, project_id=first.project_id)["total_receipts"] == 1


def test_scope_switch_does_not_double_count_gaps(setup):
    capture(setup)
    capture(setup, selection=False)
    capture(setup)
    row = report(setup[1])["records"][0]
    assert row["evolution"]["earlier_history_gap"]
    assert row["between_changes"] == []
    assert row["between_comparison"] == "no_adjacent_comparable_evolution"


@pytest.mark.parametrize("mutation", ["revision", "event", "receipt", "head", "remove_revision"])
def test_tampering_never_retains_reconstruction_claim(setup, mutation):
    capture(setup)
    store = setup[1]
    with sql(store) as db:
        if mutation == "revision":
            db.execute("UPDATE observed_revisions SET payload=?", (zlib.compress(b'{}'),))
        elif mutation == "event":
            raw = db.execute("SELECT payload FROM session_evolution").fetchone()[0]
            data = json.loads(raw)
            data["before_revision"] = "0" * 64
            db.execute("UPDATE session_evolution SET payload=?", (json.dumps(data).encode(),))
        elif mutation == "receipt":
            raw = db.execute("SELECT payload FROM receipts").fetchone()[0]
            data = json.loads(raw)
            data["elapsed_ms"] += 1
            import rfc8785
            db.execute("UPDATE receipts SET payload=?", (rfc8785.dumps(data),))
        elif mutation == "head":
            db.execute("UPDATE evolution_heads SET digest=?", ("0" * 64,))
        else:
            db.execute("DELETE FROM observed_revisions")
    result = report(store)
    assert result["records"][0]["evolution"]["status"] == "broken"
    assert result["periods"]["history"]["reconstructable_changes"] == 0
    assert result["periods"]["history"]["meaningful_changes"] == 1


def test_broken_parent_propagates(setup):
    first = capture(setup)
    capture(setup)
    store = setup[1]
    with sql(store) as db:
        db.execute("UPDATE session_evolution SET digest=? WHERE session_id=?", ("a" * 64, first.session_id))
    assert all(r["evolution"]["status"] == "broken" for r in report(store)["records"])


def test_missing_revision_retains_original_gap_denominator(setup):
    capture(setup)
    (setup[0] / "gap.py").write_text("gap = True\n")
    capture(setup)
    store = setup[1]
    with sql(store) as db:
        db.execute("DELETE FROM observed_revisions")
    stats = report(store)["periods"]["history"]
    assert (stats["meaningful_changes"], stats["between_session_changes"]) == (3, 1)
    assert stats["reconstructable_changes"] == 0
    assert stats["reconstructable_change_rate"] == 0
    assert stats["incomplete_history_receipts"] == 0


def test_inconsistent_event_counts_make_percentage_unavailable(setup):
    capture(setup)
    store = setup[1]
    with sql(store) as db:
        raw = db.execute("SELECT payload FROM session_evolution").fetchone()[0]
        data = json.loads(raw)
        data["during_counts"]["files"] = 99
        import rfc8785
        updated = rfc8785.dumps(data)
        identity = digest("forkit-session-event-v1", updated)
        db.execute("UPDATE session_evolution SET payload=?, digest=?", (updated, identity))
        db.execute("UPDATE evolution_heads SET digest=?", (identity,))
    result = report(store)
    stats = result["periods"]["history"]
    assert result["records"][0]["evolution"]["status"] == "broken"
    assert stats["meaningful_changes"] == 1
    assert stats["reconstructable_changes"] == 0
    assert stats["reconstructable_change_rate"] is None
    assert stats["incomplete_history_receipts"] == 1


@pytest.mark.parametrize("raw", [b"", b"not-zlib", zlib.compress(b"{}")[:-1], zlib.compress(b"{}") + b"trailing", zlib.compress(b"x" * 1_048_577)])
def test_bounded_decompression(raw):
    with pytest.raises(ContractError):
        unpack(raw)


def test_missing_passport_and_recovery_stay_in_denominator(setup):
    capture(setup, selection=False)
    capture(setup, outcome="recovered")
    result = report(setup[1])
    stats = result["periods"]["history"]
    assert stats["meaningful_changes"] == 2 and stats["reconstructable_changes"] == 0
    assert result["records"][0]["trace"] == "session_end_unknown"


def test_dependency_manifest_lock_and_file_count_once(setup):
    project, store, *_ = setup
    start, _ = store.start(project, tool="codex", selection=setup[2])
    (project / "package.json").write_text(json.dumps({"dependencies": {"stripe": "^1.0.0"}}))
    (project / "package-lock.json").write_text(json.dumps({"lockfileVersion": 3, "packages": {"node_modules/stripe": {"version": "1.0.0"}}}))
    store.finish(start.session_id)
    result = report(store)
    row = result["records"][0]
    assert len(row["receipt"]["file_changes"]) == 2
    assert len(row["changes"]) == 1 and len(row["changes"][0]["details"]) == 2
    assert result["periods"]["history"]["reconstructable_changes"] == 1


def test_partial_metadata_never_manufactures_removal(setup):
    project, store, *_ = setup
    (project / "package.json").write_text('{"dependencies":{"stripe":"1.0.0"}}')
    start, _ = store.start(project, tool="codex", selection=setup[2])
    (project / "package.json").write_text('{ malformed')
    store.finish(start.session_id)
    row = report(store)["records"][0]
    assert row["partial"]
    assert not any(c["category"] == "dependencies" for c in row["changes"])


def test_calendar_totals_include_receipts_beyond_display_limit(setup):
    for moment in ("2026-09-13T21:59:00Z", "2026-09-13T22:01:00Z", "2026-09-14T10:00:00Z", "2026-09-15T10:00:00Z"):
        with patch("forkit_radar.sessions.storage.now", return_value=moment):
            capture(setup)
    result = build(setup[1], timezone_name="Europe/Berlin", at=datetime(2026, 9, 14, 12, tzinfo=timezone.utc), limit=1)
    assert (result["displayed_receipts"], result["total_receipts"], result["future_dated_receipts"]) == (1, 4, 1)
    assert result["periods"]["today"]["receipts"] == 2
    assert result["periods"]["week"]["receipts"] == 2
    assert result["periods"]["history"]["receipts"] == 4


def test_timezone_dst_and_invalid_inputs():
    tz, name = zone("Europe/Berlin")
    assert name == "Europe/Berlin"
    assert datetime(2026, 3, 29, 0, 30, tzinfo=timezone.utc).astimezone(tz).hour == 1
    assert datetime(2026, 3, 29, 1, 30, tzinfo=timezone.utc).astimezone(tz).hour == 3
    for value in ("not-a-real-zone", "/etc/passwd", "../secret", "x" * 81):
        with pytest.raises(ContractError):
            zone(value)


def test_legacy_read_then_atomic_upgrade_preserves_receipts(setup):
    first = capture(setup)
    store = setup[1]
    with sql(store) as db:
        for table in ("evolution_heads", "session_evolution", "observed_revisions"):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=1")
        raw = db.execute("SELECT payload FROM receipts").fetchone()[0]
    original = (store.root / store.database_name).read_bytes()
    old = report(store)
    assert (store.root / store.database_name).read_bytes() == original
    assert old["records"][0]["trace"] == "legacy_receipt_no_retained_evolution"
    capture(setup)
    with sql(store) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2
        assert db.execute("SELECT payload FROM receipts WHERE session_id=?", (first.session_id,)).fetchone()[0] == raw
        assert db.execute("SELECT COUNT(*) FROM session_evolution").fetchone()[0] == 1
    assert report(store)["records"][0]["evolution"]["earlier_history_gap"]


def test_migration_rolls_back_on_failure(setup):
    capture(setup)
    store = setup[1]
    with sql(store) as db:
        for table in ("evolution_heads", "session_evolution", "observed_revisions"):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=1")
    with patch("forkit_radar.sessions.storage.EVOLUTION_SCHEMA", SCHEMA + ("INVALID SQL",)):
        with pytest.raises(ContractError):
            store.start(setup[0], tool="codex")
    with sql(store) as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 1
        assert not db.execute("SELECT name FROM sqlite_master WHERE name='observed_revisions'").fetchall()
    assert len(store.history()) == 1


def test_failed_evolution_write_rolls_back_finish_and_can_retry(setup):
    project, store, *_ = setup
    start, _ = store.start(project, tool="codex", selection=setup[2])
    with patch("forkit_radar.sessions.storage.append_evolution", side_effect=ContractError("injected_failure")):
        with pytest.raises(ContractError):
            store.finish(start.session_id)
    assert store.active()[0].started.session_id == start.session_id
    assert not store.history()
    store.finish(start.session_id)
    assert report(store)["records"][0]["trace"] == "complete"


def test_view_does_not_reread_projects_or_use_network(setup):
    capture(setup)
    def forbidden(*_args, **_kwargs):
        raise AssertionError("external operation")
    with patch("socket.socket", forbidden), patch("subprocess.Popen", forbidden), patch("forkit_radar.sessions.storage.capture", forbidden), patch("forkit_radar.sessions.storage.capture_metadata", forbidden):
        result = report(setup[1])
        assert b"What changed?" in render(result)
        assert b"forkit_summary_card" in encode(card(result), ".json")


def test_private_html_escaping_and_public_projection(setup):
    project, store, *_ = setup
    start, _ = store.start(project, tool="cursor", selection=setup[2])
    filename = '<img src=x onerror=alert(1)>.py'
    (project / filename).write_text("print('private source never persisted')\n")
    store.finish(start.session_id)
    result = report(store)
    raw = render(result)
    assert b'<img src=x onerror=alert(1)>' not in raw
    assert b'&lt;img src=x onerror=alert(1)&gt;.py' in raw
    assert b"private source never persisted" not in raw
    for format in (".json", ".svg", ".html"):
        public = encode(card(result), format)
        for private in (filename, setup[-1].id, str(project), "support-agent", result["records"][0]["receipt"]["session_id"]):
            assert private.encode() not in public
    assert set(json.loads(encode(card(result), ".json"))) == set(SummaryCard.model_fields)


@pytest.mark.parametrize("mutation", [{"meaningful_changes": 999}, {"reconstructable_changes": 99}, {"partial_receipts": 99}, {"passport_id": "a" * 64}, {"receipts": True}])
def test_public_summary_rejects_inconsistency_and_private_fields(setup, mutation):
    capture(setup)
    data = card(report(setup[1])).model_dump()
    data.update(mutation)
    with pytest.raises(ValueError):
        SummaryCard.model_validate(data)


def test_empty_history_does_not_create_storage(tmp_path):
    store = SessionStore(tmp_path / "absent")
    result = report(store)
    assert not store.root.exists()
    assert result["periods"]["week"]["reconstructable_change_rate"] is None
    assert b"No receipts in this view yet" in render(result)
    assert b"No changes yet" in encode(card(result), ".svg")


def test_digest_domains_are_distinct():
    raw = b"{}"
    assert len({digest(domain, raw) for domain in ("forkit-session-event-v1", "forkit-session-revision-v1", "forkit-session-receipt-v1")}) == 3
    assert digest("forkit-session-revision-v1", raw) != hashlib.sha256(raw).hexdigest()


def test_limit_and_project_inputs_are_checked(setup):
    for limit in (0, 1001, True):
        with pytest.raises(ContractError):
            build(setup[1], limit=limit)
    with pytest.raises(ValueError):
        build(setup[1], project_id="not-an-id")


def test_evolution_and_receipt_commit_together(setup):
    receipt = capture(setup)
    with setup[1]._connect() as db:
        observed = list(verify(db))
    assert observed[0][0] == receipt and observed[0][1]["status"] == "consistent"
