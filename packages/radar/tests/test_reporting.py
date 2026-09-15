"""Privacy projection, consent, exact previews and failure-safe local reporting."""
from __future__ import annotations

import hashlib
import json
import sqlite3
import subprocess
from datetime import date
from unittest.mock import patch

import pytest
from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport

from forkit_radar.identity.storage import canonical
from forkit_radar.jsonio import ContractError
from forkit_radar.reporting import client
from forkit_radar.reporting.contracts import Contribution, Discovery, Week
from forkit_radar.reporting.projection import build
from forkit_radar.reporting.storage import ReportingStore
from forkit_radar.sessions.details import Selection
from forkit_radar.sessions.storage import SessionStore

ENDPOINT = "http://127.0.0.1:8766/api/v1/radar"


@pytest.fixture
def local(tmp_path):
    project = tmp_path / "SECRET-project"
    project.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)
    (project / "PRIVATE-name.py").write_text("SECRET-source = 1\n")
    sessions = SessionStore(tmp_path / "private")
    reporting = ReportingStore(sessions.root)
    registry = LocalRegistry(tmp_path / "registry")
    model = ModelPassport(name="PRIVATE-model", version="1.0", creator={"name": "Fixture"}, task_type="text-generation", architecture="transformer")
    agent = AgentPassport(name="PRIVATE-agent", version="1.0", creator={"name": "Fixture"}, model_id=model.id, task_type="customer-support", architecture="ReAct")
    registry.register_model(model)
    registry.register_agent(agent)
    return project, sessions, reporting, Selection(registry=str(tmp_path / "registry"), passport_id=agent.id), agent


def capture(local, moment="2026-09-16T11:00:00Z"):
    project, sessions, _, selection, *_ = local
    with patch("forkit_radar.sessions.storage.now", return_value=moment):
        start, _ = sessions.start(project, tool="codex", selection=selection)
        with (project / "PRIVATE-name.py").open("a") as f:
            f.write("change = True\n")
        return sessions.finish(start.session_id)


def enabled(local):
    local[2].enable(ENDPOINT, allow_local=True)
    return local[2]


def packet(local):
    return build(local[1], local[2], 1, at=date(2026, 9, 16))


def test_disabled_default_never_creates_state_or_sends(local):
    p, sessions, reporting, *_ = local
    assert reporting.status()["state"] == "disabled"
    reporting.operation("scan", {})
    assert not reporting.root.exists()
    with patch("socket.socket", side_effect=AssertionError("network")):
        capture(local)
    assert not (reporting.root / reporting.database_name).exists()
    assert len(sessions.history()) == 1


def test_projection_reuses_retained_receipts_without_private_fields(local):
    first = capture(local, "2026-09-14T11:00:00Z")
    capture(local, "2026-09-15T11:00:00Z")
    enabled(local)  # Explicit previews can include retained pre-consent receipts.
    result = packet(local)
    last = result.weeks[-1]
    assert (last.receipts, last.meaningful_changes, last.reconstructable_changes) == (2, 2, 2)
    assert last.active_days == 2 and last.active_passports == 1
    raw = canonical(result)
    for secret in (str(local[0]), local[-1].id, "PRIVATE-model", "PRIVATE-agent", "PRIVATE-name.py", first.session_id, "SECRET-source"):
        assert secret.encode() not in raw
    assert set(json.loads(raw)) == set(Contribution.model_fields)


def test_calendar_weeks_exclude_old_and_future_receipts(local):
    for moment in ("2026-08-23T23:59:00Z", "2026-08-24T00:01:00Z", "2026-09-17T00:00:00Z"):
        capture(local, moment)
    enabled(local)
    result = packet(local)
    assert sum(w.receipts for w in result.weeks) == 1
    assert result.weeks[0].start == "2026-08-24"


def test_local_creation_dedup_and_scan_journal(local):
    store = enabled(local)
    for _ in range(2):
        store.operation("passport", {}, identity="passport:" + local[-1].id, observed_on="2026-09-15")
    discovery = Discovery(observed_on="2026-09-16", models=3, agents=2, mcp_servers=1, applications_and_processes=2, partial=True)
    store.operation("scan", {"successful": False, "discovery": discovery.model_dump()}, observed_on="2026-09-16")
    result = packet(local)
    assert result.weeks[-1].passport_versions_created == 1
    assert result.weeks[-1].scans == 1 and result.weeks[-1].successful_scans == 0
    assert result.latest_discovery.models == 3
    assert result.weeks[-1].active_days == 1  # Creating a Passport alone is not a repeat scan.


def test_disable_preserves_sessions_and_stops_journal(local, tmp_path):
    capture(local)
    store = enabled(local)
    store.disable()
    store.operation("passport", {}, identity="ignored")
    with pytest.raises(ContractError, match="disabled"):
        client.preview(local[1], store, tmp_path / "preview.json")
    assert len(local[1].history()) == 1
    with store._connect() as db:
        assert db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 0


@pytest.mark.parametrize("value", [
    "http://example.com/api/v1/radar", "https://user:secret@example.com/api/v1/radar",
    "https://example.com/api/v1/radar?token=secret", "https://example.com/api/v1/radar#x",
    "https://example.com/other", "file:///api/v1/radar", "https://example.com:99999/api/v1/radar",
    "https://example.com\\@evil/api/v1/radar", "http://localhost/api/v1/radar",
    "https://example.com/\napi/v1/radar", "https://example.com:0/api/v1/radar",
])
def test_endpoint_rules(value):
    with pytest.raises(ContractError):
        client.checked_endpoint(value, allow_local=True)


def test_loopback_requires_explicit_selection():
    with pytest.raises(ContractError):
        client.checked_endpoint(ENDPOINT)
    assert client.checked_endpoint(ENDPOINT, allow_local=True) == ENDPOINT
    assert client.checked_endpoint("https://example.org/api/v1/radar") == "https://example.org/api/v1/radar"


def test_exact_preview_excludes_credential_and_refuses_overwrite(local, tmp_path):
    store = enabled(local)
    target = tmp_path / "preview.json"
    with patch("socket.socket", side_effect=AssertionError("network")):
        result, digest = client.preview(local[1], store, target)
    with store._connect() as db:
        secret = store._profile(db)["credential"]
    assert secret not in target.read_text() and secret not in json.dumps(store.status())
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    with pytest.raises(OSError):
        client.preview(local[1], store, target)
    assert hashlib.sha256(target.read_bytes()).hexdigest() == digest
    assert target.stat().st_mode & 0o777 == 0o600
    assert result.surface_id == store.status()["surface_id"]


def test_modified_preview_never_reaches_transport(local, tmp_path):
    store = enabled(local)
    target = tmp_path / "preview.json"
    _, digest = client.preview(local[1], store, target)
    target.write_bytes(target.read_bytes() + b"\n")
    with patch.object(client, "request", side_effect=AssertionError("unexpected send")):
        with pytest.raises(ContractError, match="digest"):
            client.send(store, target, digest)


def test_exact_retry_and_uncertain_ack_preserve_payload(local, tmp_path):
    store = enabled(local)
    target = tmp_path / "preview.json"
    original, digest = client.preview(local[1], store, target)
    with patch.object(client, "request", side_effect=ContractError("uncertain")):
        with pytest.raises(ContractError):
            client.send(store, target, digest)
    assert store.status()["last_sent_sequence"] == 0
    with patch.object(client, "request") as transport:
        client.send(store, target, digest)
        assert transport.call_args.args[2] == original.payload
        client.send(store, target, digest)
        assert transport.call_args.args[2] == original.payload
    assert store.status()["last_sent_sequence"] == original.payload.sequence



@pytest.mark.parametrize("field,value", [("status", []), ("payload_sha256", "0" * 64), ("accepted_sequence", "1")])
def test_invalid_collector_ack_never_confirms_send(local, tmp_path, field, value):
    store = enabled(local)
    target = tmp_path / "preview.json"
    original, digest = client.preview(local[1], store, target)
    ack = {"schema_version": "1.0", "status": "stored", "accepted_sequence": original.payload.sequence,
           "payload_sha256": hashlib.sha256(canonical(original.payload)).hexdigest()}
    ack[field] = value
    with patch("forkit_radar.reporting.client.http.client.HTTPConnection") as connection:
        response = connection.return_value.getresponse.return_value
        response.status = 200
        response.read.return_value = json.dumps(ack).encode()
        with pytest.raises(ContractError, match="invalid_publication_confirmation"):
            client.send(store, target, digest)
        connection.return_value.close.assert_called_once()
    assert store.status()["last_sent_sequence"] == 0


def test_endpoint_switch_requires_withdrawal(local):
    store = enabled(local)
    before = store.status()["surface_id"]
    with pytest.raises(ContractError, match="withdraw"):
        store.enable("https://another.example/api/v1/radar")
    store.disable()
    with patch.object(client, "request", side_effect=ContractError("offline")):
        with pytest.raises(ContractError):
            client.withdraw(store)
    assert store.status()["state"] == "disabled"
    with patch.object(client, "request"):
        client.withdraw(store)
    assert store.status()["state"] == "withdrawn"
    store.enable("https://another.example/api/v1/radar")
    assert store.status()["surface_id"] != before


def test_bad_retained_state_does_not_claim_reconstruction(local):
    capture(local)
    enabled(local)
    with sqlite3.connect(local[1].root / "sessions.sqlite3") as db:
        db.execute("DELETE FROM observed_revisions")
    result = packet(local)
    assert result.weeks[-1].meaningful_changes == 1
    assert result.weeks[-1].reconstructable_changes == 0


@pytest.mark.parametrize("field,value", [
    ("receipts", True), ("receipts", -1), ("receipts", 1.0), ("receipts", 100_000_001),
    ("start", "2026-02-30"), ("start", "2026-09-15"), ("active_days", 8),
    ("successful_scans", 1), ("meaningful_changes", 1), ("active_passports", 1),
    ("private_name", "secret"), ("reconstructable_changes", 1),
])
def test_invalid_public_week(field, value):
    data = Week(start="2026-09-14").model_dump()
    data[field] = value
    with pytest.raises(ValueError):
        Week.model_validate(data)


def test_private_or_out_of_window_contribution_rejected(local):
    enabled(local)
    original = packet(local).model_dump(mode="json")
    for mutation in ({"passport_id": local[-1].id}, {"generated_on": "2026-09-23"}, {"sequence": True}, {"latest_discovery": {"url": "secret"}}):
        data = dict(original, **mutation)
        with pytest.raises(ValueError):
            Contribution.model_validate(data)


def test_journal_limit_fails_preview_explicitly(local, tmp_path):
    store = enabled(local)
    with store._connect(write=True) as db:
        db.executemany("INSERT INTO operations VALUES (?, '2026-09-16', 'passport', ?)",
                       [(str(i), b"{}") for i in range(10_000)])
    store.operation("passport", {})
    assert not store.status()["journal_complete"]
    with pytest.raises(ContractError, match="incomplete"):
        client.preview(local[1], store, tmp_path / "preview.json")


def test_plain_cli_enable_and_preview_do_not_use_network(local, tmp_path, capsys):
    from forkit_radar.cli import main
    args = ["--store", str(local[1].root)]
    with patch("socket.socket", side_effect=AssertionError("network")):
        assert main(["metrics", "status", *args]) == 0
        assert main(["metrics", "enable", "--endpoint", ENDPOINT, "--allow-local-collector", *args]) == 0
        assert main(["metrics", "preview", "--output", str(tmp_path / "preview.json"), *args]) == 0
    assert "Nothing sent" in capsys.readouterr().out


def test_unselected_and_failed_discovery_categories_are_unknown(local):
    from types import SimpleNamespace

    from forkit_radar.discovery.types import scope_keys
    from forkit_radar.reporting.storage import note_scan

    enabled(local)
    absent = SimpleNamespace(observation=SimpleNamespace(manifest=None))
    report = SimpleNamespace(sources=[SimpleNamespace(scope=scope_keys("ollama")[0], status="missing", findings=[absent])])
    with patch("forkit_radar.reporting.storage.today", return_value="2026-09-16"):
        note_scan(local[1].root, report)
    result = packet(local)
    assert result.latest_discovery.models == 0
    assert result.latest_discovery.agents is None
    report.sources[0].status = "denied"
    with patch("forkit_radar.reporting.storage.today", return_value="2026-09-16"):
        note_scan(local[1].root, report)
    result = packet(local)
    assert result.latest_discovery.models is None
    assert result.latest_discovery.partial
    assert result.weeks[-1].successful_scans == 1 and result.weeks[-1].scans == 2
