"""Public export privacy, conservative semantics and local-only CLI outputs."""

import json
import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from pydantic import ValidationError

from forkit_radar.cli import main
from forkit_radar.sessions.cards import Counts, Prior, SessionCard, encode, project, svg
from forkit_radar.sessions.models import Receipt
from forkit_radar.sessions.storage import SessionStore

PRIVATE = "private_client_xa91"


@pytest.fixture
def saved(tmp_path):
    root = tmp_path / PRIVATE
    root.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(root)], check=True)
    (root / "main.py").write_text("print('before')")
    store = SessionStore(tmp_path / "store")
    store.finish(store.start(root, tool="codex")[0].session_id)
    start, _ = store.start(root, tool="codex")
    (root / (PRIVATE + ".py")).write_text("print('do not export source')")
    (root / "package.json").write_text(json.dumps({"dependencies": {PRIVATE: "1.2.3"}}))
    receipt = store.finish(start.session_id)
    return store, receipt


def test_public_projection_and_schema(saved):
    _, receipt = saved
    card = project(receipt)
    assert card.file_changes == 2
    assert card.dependencies.added == 1
    assert card.since_previous.state == "complete"
    assert card.between_sessions.files == 0
    assert card.tool_basis == "user_selected"
    schema_path = Path(__file__).parents[1] / "src/forkit_radar/sessions/session-card-v1.schema.json"
    assert json.loads(schema_path.read_text()) == SessionCard.model_json_schema()
    for format in (".json", ".svg", ".html"):
        result = encode(card, format).decode()
        for private in (PRIVATE, receipt.session_id, receipt.project_id, receipt.started_at,
                        "package.json", "1.2.3", "do not export source"):
            assert private not in result
    # Projection is a separate aggregate contract, never a redacted private record.
    assert "file_changes" not in Prior.model_fields
    assert card.runtime == "not_observed"


@pytest.mark.parametrize("field,value", [
    ("session_id", "a" * 36), ("passport_id", "a" * 64), ("title", "hello"),
    ("tool", "<script>alert(1)</script>"), ("file_changes", True),
    ("file_changes", 4001), ("file_changes", -1), ("runtime", "verified"),
    ("elapsed_minutes", "42"), ("possible_renames", 2001),
])
def test_card_rejects_free_text_coercion_and_out_of_scope(saved, field, value):
    card = project(saved[1])
    with pytest.raises(ValidationError):
        SessionCard.model_validate({**card.model_dump(), field: value})


@pytest.mark.parametrize("model,data", [
    (Counts, {"state": "not_captured", "added": 0}),
    (Counts, {"state": "complete"}),
    (Counts, {"state": "complete", "added": 3000, "removed": 3000, "changed": 0}),
    (Prior, {"state": "no_baseline", "files": 0}),
    (Prior, {"state": "partial"}),
])
def test_unknown_is_not_zero(model, data):
    with pytest.raises(ValidationError):
        model.model_validate(data)


def test_revalidation_at_projection_and_render(saved):
    receipt = saved[1]
    with pytest.raises(ValidationError):
        project(receipt.model_copy(update={"tool": "private"}))
    with pytest.raises(ValidationError):
        svg(project(receipt).model_copy(update={"tool": "<script>"}))


def test_legacy_and_recovery_remain_unknown(saved):
    original = saved[1]
    raw = {k: v for k, v in original.model_dump().items() if k in Receipt.model_fields}
    raw.update(schema_version="1.0", passport_id=None, dependency_comparison="not_available",
               configuration_comparison="not_available", elapsed_ms=None, duration_basis="unknown",
               status="interrupted", outcome="recovered", comparison="partial")
    card = project(Receipt.model_validate(raw))
    assert card.dependencies.state == "not_captured"
    assert card.dependencies.added is None
    assert card.since_previous.state == "not_captured"
    assert card.elapsed_minutes is None
    drawing = svg(card)
    assert "At least" in drawing and "duration unknown" in drawing
    assert "Includes interval until recovery" in drawing
    assert "Not captured" in drawing


@pytest.mark.parametrize("format", [".html", ".svg", ".json"])
def test_cli_card_read_only_exclusive_private_mode(saved, tmp_path, capsys, format):
    store, receipt = saved
    db = tmp_path / "store/sessions.sqlite3"
    with sqlite3.connect(db) as connection:
        before = list(connection.iterdump())
    output = tmp_path / ("receipt" + format)
    args = ["card", receipt.session_id, "--store", str(tmp_path / "store"), "--output", str(output)]
    assert main(args) == 0
    capsys.readouterr()
    assert output.stat().st_mode & 0o777 == 0o600
    expected = output.read_bytes()
    assert main(args) == 2
    assert output.read_bytes() == expected
    assert store.receipt(receipt.session_id) == receipt
    with sqlite3.connect(db) as connection:
        assert list(connection.iterdump()) == before


def test_stdout_is_public_and_bad_extension_creates_nothing(saved, tmp_path, capsys):
    args = ["card", "--store", str(tmp_path / "store")]
    assert main([*args, "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert SessionCard.model_validate(data).privacy == "aggregate_only"
    bad = tmp_path / "receipt.png"
    assert main([*args, "--output", str(bad)]) == 2
    assert not bad.exists()


def test_symlink_destination_refused(saved, tmp_path):
    victim = tmp_path / "victim.html"
    victim.write_text("untouched")
    output = tmp_path / "card.html"
    output.symlink_to(victim)
    assert main(["card", "--store", str(tmp_path / "store"), "--output", str(output)]) == 2
    assert victim.read_text() == "untouched"


def test_self_contained_html_and_no_network_calls(saved, monkeypatch):
    import socket

    def forbidden(*_args, **_kwargs):
        pytest.fail("Card attempted a network connection")

    monkeypatch.setattr(socket.socket, "connect", forbidden)
    output = encode(project(saved[1]), ".html").decode()
    assert "connect-src 'none'" in output
    assert "script-src 'sha256-" in output
    assert 'src="http' not in output and 'href="http' not in output
    assert "toBlob" in output and "image/png" in output
    assert "document.write" not in output and "innerHTML" not in output
    assert os.environ.get("FORKIT_TOKEN") is None or "FORKIT_TOKEN" not in output
