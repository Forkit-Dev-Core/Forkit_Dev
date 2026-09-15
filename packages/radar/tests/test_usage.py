"""Real local receipt reuse, privacy, consent, retries and concurrent updates."""

import json
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from types import SimpleNamespace as NS
from unittest.mock import Mock, patch

import pytest

from forkit_radar.cli import main
from forkit_radar.identity.storage import canonical
from forkit_radar.reporting.storage import ReportingStore
from forkit_radar.reporting.usage_capture import receipt, safely_record, scan
from forkit_radar.reporting.usage_contracts import UsageContribution
from forkit_radar.reporting.usage_storage import UsageStore
from forkit_radar.reporting.usage_worker import begin_withdrawal, deliver, kick, supervise, withdraw
from forkit_radar.sessions.storage import SessionStore

ENDPOINT = "http://127.0.0.1:8766/api/v1/radar"
NOW = datetime(2026, 9, 15, 12, tzinfo=timezone.utc)


@pytest.fixture
def state(tmp_path, monkeypatch):
    monkeypatch.setenv("FORKIT_USAGE_STORE", str(tmp_path / "usage"))
    monkeypatch.setenv("CI", "1")
    with patch("forkit_radar.reporting.usage_storage.today", return_value=NOW.date()):
        yield UsageStore(tmp_path / "usage")


def enable(state, now=0):
    state.enable(ENDPOINT, consent="usage-v2", validation=True, allow_local=True, now=now)
    return state


def event(state, key="local-secret-receipt", when=NOW):
    state.event(
        "receipt",
        key,
        dict(receipts=1, during_changes=3, reconstructable_changes=2),
        selected="codex",
        passports=["SECRET-passport"],
        observed=when,
    )


def test_default_and_old_consent_cannot_enable_automatic_reporting(state):
    with patch("socket.socket", side_effect=AssertionError("no network")):
        safely_record("passport", "SECRET")
        assert state.status()["state"] == "disabled"
        assert not state.root.exists()
        ReportingStore(state.root).enable(ENDPOINT, True)
        safely_record("passport", "SECRET")
    assert not (state.root / state.database_name).exists()


def test_consent_and_validation_boundaries(state, monkeypatch):
    for kwargs in (
        {"consent": "old"},
        {"consent": "usage-v2", "allow_local": True},
        {"consent": "usage-v2"},
    ):
        with pytest.raises(ValueError):
            state.enable(ENDPOINT, **kwargs)
    assert not state.root.exists()


def test_requires_first_result_before_consent(state, tmp_path):
    assert (
        main(
            [
                "usage",
                "enable",
                "--endpoint",
                ENDPOINT,
                "--consent",
                "usage-v2",
                "--validation",
                "--allow-local-collector",
                "--store",
                str(tmp_path / "absent"),
            ]
        )
        == 2
    )
    assert not state.root.exists()


def test_no_backfill_except_explicit_latest(state):
    enable(state, NOW.timestamp())
    event(state, when=datetime(2026, 9, 14, 12, tzinfo=timezone.utc))
    assert sum(d.receipts for d in state.preview().days) == 0
    state.event(
        "receipt",
        "explicit-latest",
        dict(receipts=1),
        selected="other",
        observed=datetime(2026, 9, 14, 12, tzinfo=timezone.utc),
        include_previous=True,
    )
    assert sum(d.receipts for d in state.preview().days) == 1


def test_deduplicates_across_projects_and_cannot_leak_identifiers(state):
    enable(state)
    for _ in range(3):
        event(state)
    event(UsageStore(state.root), key="second-project-receipt")
    packet = state.preview()
    assert sum(d.receipts for d in packet.days) == 2
    raw = canonical(packet)
    for secret in (
        b"SECRET",
        b"local-secret",
        str(state.root).encode(),
        b"surface_id",
        b"credential",
    ):
        assert secret not in raw
    assert packet.passport_windows[-1].distinct_passports == 0  # today excluded
    assert packet.days[-1].session_tools.codex == 2


def test_concurrent_capture_records_one_original(state):
    enable(state)
    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(lambda _: event(state), range(12)))
    assert sum(d.receipts for d in state.preview().days) == 1


def test_passport_dedup_survives_event_retention(state):
    enable(state)
    state.event("passport", "SECRET", dict(passport_versions_created=1), observed=NOW)
    with state._connect(write=True) as db:
        db.execute("DELETE FROM events")
    state.event("passport", "SECRET", dict(passport_versions_created=1), observed=NOW)
    assert sum(d.passport_versions_created for d in state.preview().days) == 0


def test_fixed_tool_presence_is_distinct_from_declared_session_tool(state):
    enable(state)

    def finding(name):
        return NS(observation=NS(manifest=NS(declared_identity=NS(name=NS(value=name)))))

    report = NS(
        scan_id="secret-scan",
        finished_at="2026-09-15T12:00:00Z",
        sources=[
            NS(detector="agent-manifest", status="complete", findings=[finding("Cursor")]),
            NS(
                detector="applications",
                status="complete",
                findings=[finding("Codex"), finding("Codex")],
            ),
        ],
    )
    scan(state, report)
    event(state)
    r = state.preview().days[-1]
    assert r.detected_tools == ("codex",)
    assert r.detection_observations == 3 and r.session_tools.codex == 1


def test_24_hour_limit_including_concurrent_commands(state):
    enable(state)
    event(state)
    transport = Mock()
    with ThreadPoolExecutor(max_workers=4) as pool:
        list(pool.map(lambda _: deliver(state, now=NOW.timestamp(), transport=transport), range(8)))
    assert transport.call_count == 1
    assert not deliver(state, now=NOW.timestamp() + 86399, transport=transport)
    assert deliver(state, now=NOW.timestamp() + 86400, transport=transport)
    assert transport.call_count == 2


def test_lost_ack_retries_identical_snapshot_then_refreshes(state):
    enable(state)
    event(state)
    sent = []

    def lose(p, m, packet, **kwargs):
        sent.append(canonical(packet))
        raise OSError()

    for i in range(4):
        deliver(state, now=NOW.timestamp() + i * 86400, transport=lose)
    assert sent[0] == sent[1] == sent[2]
    assert json.loads(sent[3])["sequence"] == 2
    assert state.status()["last_result"] == "unconfirmed"


def test_disable_cancels_pending_snapshot_and_keeps_local_history(state):
    enable(state)
    event(state)
    deliver(state, now=NOW.timestamp(), transport=Mock(side_effect=OSError()))
    state.disable()
    transport = Mock()
    assert not deliver(state, now=NOW.timestamp() + 86400, transport=transport)
    assert not transport.called
    with state._connect() as db:
        assert state._profile(db)["pending"] is None
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 1


def test_withdrawal_failure_stays_disabled_then_retries_and_erases(state):
    enable(state)
    event(state)
    begin_withdrawal(state)
    with pytest.raises(OSError):
        withdraw(state, transport=Mock(side_effect=OSError()))
    assert state.status()["state"] == "withdrawing"
    assert not deliver(state, transport=Mock(side_effect=AssertionError()))
    assert withdraw(state, transport=Mock())
    assert state.status()["state"] == "withdrawn"
    with state._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM events").fetchone()[0] == 0


def test_process_deadline_includes_dns_and_does_not_spawn_a_service(state):
    with patch("subprocess.run", side_effect=subprocess.TimeoutExpired("worker", 7)) as run:
        assert supervise() == 2
        assert run.call_args.kwargs["timeout"] == 7
        assert run.call_args.args[0][1:4] == ["-I", "-m", "forkit_radar.reporting.usage_worker"]
    with patch("subprocess.Popen") as popen:
        kick(state)
        assert not popen.called


def test_real_session_creation_and_receipt_view_dont_inflate(state, tmp_path):
    enable(state)
    project = tmp_path / "SECRET-project"
    project.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
    path = project / "SECRET.py"
    path.write_text("before")
    sessions = SessionStore(tmp_path / "sessions")
    with patch("forkit_radar.sessions.storage.now", return_value="2026-09-15T12:00:00Z"):
        started, _ = sessions.start(project, tool="cursor")
        path.write_text("after")
        original = sessions.finish(started.session_id)
    receipt(state, sessions, original)
    receipt(state, sessions, sessions.receipt(original.session_id))
    packet = state.preview()
    assert sum(d.receipts for d in packet.days) == 1
    assert packet.days[-1].session_tools.cursor == 1
    assert b"SECRET" not in canonical(packet)


@pytest.mark.parametrize(
    "change",
    [
        lambda p: p.update(passport_id="SECRET"),
        lambda p: p.update(sequence=True),
        lambda p: p["days"][-1].update(detected_tools=["SECRET"]),
        lambda p: p["days"][-1].update(receipts=-1),
        lambda p: p["days"][-1].update(session_tools={"codex": 1}),
        lambda p: p["days"][-1].update(date="2026-02-30"),
    ],
)
def test_strict_wire_contract(state, change):
    enable(state)
    p = state.preview().model_dump(mode="json")
    change(p)
    with pytest.raises(ValueError):
        UsageContribution.model_validate(p)
