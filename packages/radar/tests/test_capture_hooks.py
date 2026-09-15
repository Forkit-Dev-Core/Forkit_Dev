"""Real Git/SQLite lifecycle integration and adversarial callback/config boundaries."""

import argparse
import json
import select
import subprocess
import sys

import pytest

from forkit_radar.capture.cli import configuration, receive
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.cards import project as card
from forkit_radar.sessions.storage import SessionStore
from forkit_radar.sessions.summary import build


def test_first_hook_waits_for_concurrent_schema_commit(setup):
    creator_code = """
import sys
from pathlib import Path
from forkit_radar.sessions.storage import SessionStore
store = SessionStore(Path(sys.argv[1]))
with store._connect(write=True, create=True) as db:
    store._key(db)
    print('uncommitted', flush=True)
    sys.stdin.readline()
"""
    callback_code = """
import argparse, json, sys
from pathlib import Path
from forkit_radar.capture.cli import receive
args = argparse.Namespace(agent='codex', project=Path(sys.argv[2]), store=Path(sys.argv[1]),
                          agent_manifest=None, registry=None, passport_id=None)
payload = json.dumps(dict(hook_event_name='SessionStart', source='startup',
                         session_id='first-start', cwd=str(args.project))).encode()
print('ready', flush=True)
receive(args, payload)
print('captured', flush=True)
"""
    creator = subprocess.Popen(
        [sys.executable, "-I", "-B", "-c", creator_code, str(setup.store)],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    callback = None
    try:
        assert select.select([creator.stdout], [], [], 5)[0]
        assert creator.stdout.readline().strip() == b"uncommitted"
        callback = subprocess.Popen(
            [sys.executable, "-I", "-B", "-c", callback_code, str(setup.store), str(setup.project)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        assert select.select([callback.stdout], [], [], 5)[0]
        assert callback.stdout.readline().strip() == b"ready"
        # The start must wait for this real writer, not reject its temporary
        # empty schema and lose a blocking SessionStart callback.
        assert not select.select([callback.stdout], [], [], 0.2)[0]
        creator.communicate(input=b"commit\n", timeout=5)
        stdout, stderr = callback.communicate(timeout=5)
        assert callback.returncode == 0 and stdout.strip() == b"captured", stderr
        assert len(SessionStore(setup.store).active()) == 1
    finally:
        for process in (callback, creator):
            if process is not None and process.poll() is None:
                process.kill()
                process.communicate(timeout=5)


@pytest.fixture
def setup(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    subprocess.run(["git", "init", "-q", str(project)], check=True)
    (project / "main.py").write_text("x = 1\n")
    return argparse.Namespace(
        agent="codex",
        project=project,
        store=tmp_path / "store",
        agent_manifest=None,
        registry=None,
        passport_id=None,
    )


def event(args, name, **extra):
    data = dict(
        session_id="external-123",
        cwd=str(args.project),
        hook_event_name=name,
        source="startup",
        transcript_path="/never/open/secret.jsonl",
        prompt="DO_NOT_PERSIST_123",
        **extra,
    )
    if args.agent == "cursor":
        data.update(workspace_roots=[str(args.project)], is_background_agent=False)
    return json.dumps(data).encode()


@pytest.mark.parametrize(
    "agent,start,end",
    [
        ("codex", "SessionStart", "SessionEnd"),
        ("claude-code", "SessionStart", "SessionEnd"),
        ("cursor", "sessionStart", "sessionEnd"),
    ],
)
def test_hooks_capture_once_without_private_payload(setup, agent, start, end):
    setup.agent = agent
    receive(setup, event(setup, start))
    receive(setup, event(setup, start))
    (setup.project / "main.py").write_text("x = 2\n")
    receive(setup, event(setup, end))
    receive(setup, event(setup, end))
    store = SessionStore(setup.store)
    assert len(store.history()) == 1 and not store.active()
    receipt = store.receipt()
    assert len(receipt.file_changes) == 1 and receipt.tool_basis == "hook_reported"
    assert receipt.outcome == "hook_end" and receipt.elapsed_ms is not None
    assert receipt.comparison == ("partial" if agent == "cursor" else "complete")
    assert card(receipt).tool_basis == "hook_reported"
    assert build(store)["periods"]["history"]["receipts"] == 1
    raw = (setup.store / "sessions.sqlite3").read_bytes()
    assert (
        b"DO_NOT_PERSIST_123" not in raw
        and b"/never/open/" not in raw
        and b"external-123" not in raw
    )


def test_foreign_end_cannot_finish_manual_or_other_session(setup):
    store = SessionStore(setup.store)
    started, _ = store.start(setup.project, tool="cursor")
    with pytest.raises(ContractError):
        receive(setup, event(setup, "SessionEnd"))
    assert store.active()[0].started.session_id == started.session_id
    store.finish(started.session_id)
    receive(setup, event(setup, "SessionStart"))
    raw = json.loads(event(setup, "SessionEnd"))
    raw["session_id"] = "foreign"
    with pytest.raises(ContractError):
        receive(setup, json.dumps(raw).encode())
    assert len(store.active()) == 1


def test_compaction_wrong_scope_and_missing_start(setup):
    receive(setup, event(setup, "SessionEnd"))
    assert not setup.store.exists()
    raw = json.loads(event(setup, "SessionStart"))
    raw["source"] = "compact"
    receive(setup, json.dumps(raw).encode())
    assert not setup.store.exists()
    raw["source"] = "startup"
    raw["cwd"] = str(setup.project.parent)
    with pytest.raises(ContractError):
        receive(setup, json.dumps(raw).encode())
    with pytest.raises(ContractError):
        receive(setup, b"x" * 1048577)


def test_resume_preserves_prior_history_and_recovery(setup):
    receive(setup, event(setup, "SessionStart"))
    store = SessionStore(setup.store)
    store.finish(store.active()[0].started.session_id, outcome="recovered")
    receive(setup, event(setup, "SessionStart"))
    receive(setup, event(setup, "SessionEnd"))
    assert len(store.history()) == 2
    assert store.history()[1].comparison == "partial"


def test_configuration_uses_official_shapes_and_quotes_paths(setup):
    setup.store = setup.store.parent / "space ' and $(private)"
    for agent in ("codex", "claude-code", "cursor"):
        setup.agent = agent
        config = configuration(setup, setup.project)
        if agent == "cursor":
            assert config["version"] == 1 and set(config["hooks"]) == {"sessionStart", "sessionEnd"}
        else:
            assert set(config["hooks"]) == {"SessionStart", "SessionEnd"}
            assert config["hooks"]["SessionEnd"][0]["hooks"][0]["timeout"] <= 10
        assert "--store" in json.dumps(config) and "transcript" not in json.dumps(config)


@pytest.mark.parametrize("foreign", [False, True])
def test_duplicate_start_winner_is_reused_but_foreign_winner_is_refused(
    setup, monkeypatch, foreign
):
    start = SessionStore.start
    first = True

    def competing_start(store, *args, **kwargs):
        nonlocal first
        if first:
            first = False
            winning = {**kwargs, "hook_identity": "foreign-session"} if foreign else kwargs
            start(store, *args, **winning)
        return start(store, *args, **kwargs)

    monkeypatch.setattr(SessionStore, "start", competing_start)
    if foreign:
        with pytest.raises(ContractError):
            receive(setup, event(setup, "SessionStart"))
    else:
        assert receive(setup, event(setup, "SessionStart")) == "duplicate"
    assert len(SessionStore(setup.store).active()) == 1
    raw = json.loads(event(setup, "SessionStart"))
    raw["session_id"] = "different-external-session"
    with pytest.raises(ContractError):
        receive(setup, json.dumps(raw).encode())


@pytest.mark.parametrize("point", ["before_token_check", "before_finish"])
def test_concurrent_end_does_not_report_failure_or_duplicate_receipt(setup, monkeypatch, point):
    receive(setup, event(setup, "SessionStart"))
    (setup.project / "main.py").write_text("x = 2\n")
    store = SessionStore(setup.store)
    session_id = store.active()[0].started.session_id
    if point == "before_token_check":
        check = SessionStore.matches_hook

        def competing_check(current, *args):
            current.finish(session_id, outcome="hook_end")
            return check(current, *args)

        monkeypatch.setattr(SessionStore, "matches_hook", competing_check)
        expected = "no_active_capture"
    else:
        finish = SessionStore.finish

        def competing_finish(current, *args, **kwargs):
            finish(current, *args, **kwargs)
            return finish(current, *args, **kwargs)

        monkeypatch.setattr(SessionStore, "finish", competing_finish)
        expected = "duplicate"
    assert receive(setup, event(setup, "SessionEnd")) == expected
    assert len(store.history()) == 1 and not store.active()
    assert len(store.receipt().file_changes) == 1
