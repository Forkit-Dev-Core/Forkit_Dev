"""Real Git/filesystem/CLI session receipts and failure/privacy boundaries."""

from __future__ import annotations

import json
import os
import signal
import sqlite3
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

import pytest

from forkit_radar.contracts import read_contract
from forkit_radar.identity.storage import EnrollmentStore
from forkit_radar.jsonio import ContractError
from forkit_radar.sessions.cli import render
from forkit_radar.sessions.clock import stamp
from forkit_radar.sessions.inventory import allowed, difference, git
from forkit_radar.sessions.models import ClockStamp, FileState, Snapshot, elapsed
from forkit_radar.sessions.storage import SessionStore

SECRET = "SESSION_SECRET_SENTINEL_672c4b"
FIXTURES = Path(__file__).parent / "fixtures"


def run_git(project, *args):
    return subprocess.run(["/usr/bin/git", *args], cwd=project, check=True, capture_output=True)


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    run_git(root, "init", "-q")
    (root / "main.py").write_text("print('initial')\n")
    (root / "unchanged.py").write_text("print('unchanged')\n")
    run_git(root, "add", ".")
    run_git(
        root,
        "-c",
        "user.name=Fixture",
        "-c",
        "user.email=fixture@example.invalid",
        "commit",
        "-qm",
        "Fixture baseline",
    )
    return root


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "state")


def cli(store, *args, cwd=None):
    return subprocess.run(
        [sys.executable, "-m", "forkit_radar.cli", *args, "--store", str(store.root)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=20,
    )


def test_real_session_dirty_baseline_and_restart(project, store):
    (project / "main.py").write_text("preexisting uncommitted edit\n")
    before_index = (project / ".git/index").read_bytes()
    started, _ = store.start(project, tool="codex")
    (project / "fresh.ts").write_text("export const answer = 42;\n")
    receipt = SessionStore(store.root).finish(started.session_id)
    assert [(c.kind, c.path) for c in receipt.file_changes] == [("added", "fresh.ts")]
    assert receipt.elapsed_ms is not None and receipt.elapsed_ms >= 0
    assert receipt.comparison == "complete"
    assert SessionStore(store.root).receipt() == receipt
    assert (project / ".git/index").read_bytes() == before_index
    assert run_git(project, "rev-list", "--count", "HEAD").stdout.strip() == b"1"


def test_same_size_same_mtime_edit_detected(project, store):
    source = project / "main.py"
    original = source.stat()
    started, _ = store.start(project, tool="cursor")
    source.write_text("print('changed')\n")
    os.utime(source, ns=(original.st_atime_ns, original.st_mtime_ns))
    receipt = store.finish(started.session_id)
    assert [(c.kind, c.path) for c in receipt.file_changes] == [("modified", "main.py")]


def test_removals_and_exact_rename_candidates(project, store):
    started, _ = store.start(project, tool="other")
    (project / "main.py").rename(project / "renamed.py")
    (project / "unchanged.py").unlink()
    receipt = store.finish(started.session_id)
    assert {c.kind for c in receipt.file_changes} == {"possible_rename", "removed"}
    rename = next(c for c in receipt.file_changes if c.kind == "possible_rename")
    assert (rename.previous_path, rename.path) == ("main.py", "renamed.py")


def test_identical_files_do_not_create_guessed_rename(project, store):
    (project / "duplicate.py").write_bytes((project / "main.py").read_bytes())
    started, _ = store.start(project, tool="other")
    (project / "main.py").unlink()
    (project / "duplicate.py").unlink()
    (project / "new.py").write_text("print('initial')\n")
    receipt = store.finish(started.session_id)
    assert all(c.kind != "possible_rename" for c in receipt.file_changes)
    assert len(receipt.file_changes) == 3


def test_unchanged_and_successive_history(project, store):
    first, _ = store.start(project, tool="codex")
    a = store.finish(first.session_id)
    second, _ = store.start(project, tool="cursor")
    b = store.finish(second.session_id)
    assert not a.file_changes and not b.file_changes
    assert a.previous_session_id is None and b.previous_session_id == a.session_id
    assert store.history() == (b, a)
    assert not store.active()


def test_cloned_projects_are_distinct_local_histories(project, store, tmp_path):
    copy = tmp_path / "copy"
    run_git(tmp_path, "clone", "-q", str(project), str(copy))
    one, _ = store.start(project, tool="other")
    store.finish(one.session_id)
    two, _ = store.start(copy, tool="other")
    receipt = store.finish(two.session_id)
    assert one.project_id != two.project_id and receipt.previous_session_id is None


def test_content_and_known_sensitive_files_never_persist(project, store):
    (project / ".env").write_text(SECRET)
    (project / "credentials.py").write_text(SECRET)
    (project / "AGENTS.md").write_text(SECRET)
    (project / "secret.pem").write_text(SECRET)
    (project / "main.py").write_text(f"value = '{SECRET}'\n")
    started, snapshot = store.start(project, tool="other")
    assert {f.path for f in snapshot.files} == {"main.py", "unchanged.py"}
    receipt = store.finish(started.session_id)
    for path in store.root.iterdir():
        assert SECRET.encode() not in path.read_bytes()
        assert path.stat().st_mode & 0o777 == 0o600
    output = receipt.model_dump_json() + render(receipt, files=True)
    assert SECRET not in output and str(project) not in output
    assert "fingerprint" not in output and "boot_token" not in output


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.example",
        ".ssh/helper.py",
        ".claude/tools.py",
        "node_modules/lib/index.js",
        "secrets.py",
        "credentials.json",
        "token.py",
        "key.pem",
        "README.md",
        "chat.txt",
        "model.bin",
    ],
)
def test_scope_excludes_private_or_unsupported_files(path):
    assert not allowed(path)


def test_ignore_rule_change_is_not_removal(project, store):
    (project / "temporary.py").write_text("temporary = True\n")
    started, _ = store.start(project, tool="other")
    (project / ".gitignore").write_text("temporary.py\n")
    receipt = store.finish(started.session_id)
    assert not receipt.file_changes
    assert receipt.comparison == "partial" and receipt.unknown_count == 1


def test_symlink_replacement_is_unknown_not_deletion(project, store, tmp_path):
    secret = tmp_path / "outside.py"
    secret.write_text(SECRET)
    started, _ = store.start(project, tool="other")
    (project / "main.py").unlink()
    (project / "main.py").symlink_to(secret)
    receipt = store.finish(started.session_id)
    assert receipt.comparison == "partial" and not receipt.file_changes
    assert receipt.unknown_count == 1


def test_fifo_and_hardlink_are_not_read(project, store):
    (project / "pipe.py").write_text("tracked placeholder\n")
    run_git(project, "add", "pipe.py")
    (project / "pipe.py").unlink()
    os.mkfifo(project / "pipe.py")
    os.link(project / "main.py", project / "linked.py")
    started, snapshot = store.start(project, tool="other")
    assert set(snapshot.unknown_paths) == {"pipe.py", "linked.py", "main.py"}
    assert store.finish(started.session_id).comparison == "partial"


def test_failed_end_inventory_preserves_unknown_baseline(project, store):
    started, _ = store.start(project, tool="other")
    with patch("forkit_radar.sessions.inventory.git", side_effect=ContractError("git_unavailable")):
        receipt = store.finish(started.session_id)
    assert not receipt.file_changes and receipt.comparison == "partial"
    assert receipt.unknown_count == 2


def test_failed_start_inventory_saves_no_session(project, store):
    real_git = git

    def denied(path, *args):
        if args[0] == "ls-files":
            raise ContractError("denied")
        return real_git(path, *args)

    with (
        patch("forkit_radar.sessions.inventory.git", side_effect=denied),
        pytest.raises(ContractError),
    ):
        store.start(project, tool="other")
    assert not store.active()


def test_missing_project_can_finish_without_false_removal(project, store, tmp_path):
    started, _ = store.start(project, tool="other")
    project.rename(tmp_path / "moved")
    receipt = store.finish(started.session_id)
    assert receipt.comparison == "partial" and not receipt.file_changes


def test_concurrent_start_allows_one_active_session(project, store):
    def attempt(_):
        try:
            return store.start(project, tool="other")[0]
        except ContractError:
            return None

    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(attempt, range(4)))
    assert sum(r is not None for r in results) == 1
    assert len(store.active()) == 1


def test_finish_is_immutable_and_duplicate_stop_rejected(project, store):
    started, _ = store.start(project, tool="other")
    receipt = store.finish(started.session_id)
    with pytest.raises(ContractError, match="already_finished"):
        store.finish(started.session_id)
    assert store.receipt() == receipt and len(store.history()) == 1


def test_recovery_marks_unknown_end_and_retains_session(project, store):
    started, _ = store.start(project, tool="other")
    (project / "main.py").write_text("recovered edit\n")
    receipt = SessionStore(store.root).finish(started.session_id, outcome="recovered")
    assert receipt.status == "interrupted" and receipt.elapsed_ms is None
    assert receipt.comparison == "partial"
    assert "until recovery" in render(receipt)


def test_real_platform_continuous_clock():
    first, second = stamp(b"a" * 32), stamp(b"a" * 32)
    assert first.kind == "continuous" and elapsed(first, second) is not None
    assert elapsed(first, stamp(b"b" * 32)) is None


def test_reboot_or_backward_clock_does_not_fabricate_duration():
    first = ClockStamp(kind="continuous", milliseconds=100, boot_token="a" * 64)
    assert (
        elapsed(first, ClockStamp(kind="continuous", milliseconds=99, boot_token="a" * 64)) is None
    )
    assert (
        elapsed(first, ClockStamp(kind="continuous", milliseconds=200, boot_token="b" * 64)) is None
    )


def test_git_filters_and_fsmonitor_are_not_executed(project, store, tmp_path):
    sentinel = tmp_path / "executed"
    script = tmp_path / "filter.sh"
    script.write_text(f"#!/bin/sh\ntouch '{sentinel}'\ncat\n")
    script.chmod(0o700)
    run_git(project, "config", "filter.probe.clean", str(script))
    run_git(project, "config", "core.fsmonitor", str(script))
    (project / ".gitattributes").write_text("*.py filter=probe\n")
    started, _ = store.start(project, tool="other")
    store.finish(started.session_id)
    assert not sentinel.exists()


def test_empty_history_does_not_create_store(store):
    assert store.history() == () and store.active() == ()
    assert not store.root.exists()


def test_store_inside_project_rejected(project):
    with pytest.raises(ContractError, match="outside_project"):
        SessionStore(project / "state").start(project, tool="other")


def test_no_auto_parent_repository_selection(project, store):
    child = project / "child"
    child.mkdir()
    with pytest.raises(ContractError, match="project_root"):
        store.start(child, tool="other")


def test_session_and_enrollment_stores_share_mechanics_not_identity(project, store):
    started, _ = store.start(project, tool="other")
    from forkit_radar.identity.enrollment import preview, select_source

    manifest = project / "agent.json"
    manifest.write_bytes((FIXTURES / "manifest.json").read_bytes())
    locator, metadata = select_source(agent_file=manifest)
    entry = EnrollmentStore(store.root).propose(locator, preview(metadata))
    receipt = store.finish(started.session_id)
    assert receipt.passport_id is None
    assert EnrollmentStore(store.root).get(entry.draft.proposal_id) == entry
    assert (store.root / "sessions.sqlite3").exists() and (
        store.root / "enrollment.sqlite3"
    ).exists()


def test_public_schema_rejects_private_receipt(project, store):
    started, _ = store.start(project, tool="other")
    receipt = store.finish(started.session_id)
    with pytest.raises(ContractError):
        read_contract("public-snapshot", receipt.model_dump_json().encode())


def test_private_store_schema_tampering_rejected(project, store):
    store.start(project, tool="other")
    db = sqlite3.connect(store.root / "sessions.sqlite3")
    db.execute("CREATE TABLE injected(data TEXT)")
    db.close()
    with pytest.raises(ContractError, match="unsupported_store_schema"):
        store.active()


def test_cli_manual_account_free_first_result(project, store):
    begin = cli(store, "session", "start", "--project", str(project), "--tool", "cursor", "--json")
    assert begin.returncode == 0, begin.stderr
    session_id = json.loads(begin.stdout)["session_id"]
    (project / "main.py").write_text("print('new')\n")
    result = cli(store, "session", "stop", session_id, "--json")
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["file_changes"][0]["path"] == "main.py"
    assert "login" not in result.stdout.lower() and "signup" not in result.stdout.lower()
    assert cli(store, "receipt", session_id).returncode == 0
    assert len(json.loads(cli(store, "history", "--json").stdout)) == 1


def test_cli_wrapper_real_process_and_clean_json(project, store):
    args = [
        sys.executable,
        "-m",
        "forkit_radar.cli",
        "session",
        "run",
        "--project",
        str(project),
        "--tool",
        "other",
        "--store",
        str(store.root),
        "--json",
        "--",
        sys.executable,
        "-c",
        "from pathlib import Path; Path('main.py').write_text('edited by controlled child'); print('child output')",
    ]
    result = subprocess.run(args, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    receipt = json.loads(result.stdout)
    assert receipt["capture_mode"] == "wrapper" and receipt["outcome"] == "command_exited"
    assert len(receipt["file_changes"]) == 1 and "child output" in result.stderr
    assert b"edited by controlled child" not in (store.root / "sessions.sqlite3").read_bytes()
    assert b"print('child output')" not in (store.root / "sessions.sqlite3").read_bytes()


@pytest.mark.parametrize(
    "executable,arguments,outcome,code",
    [
        ("/missing/forkit-session-test", [], "launch_failed", 2),
        (sys.executable, ["-c", "raise SystemExit(7)"], "command_failed", 7),
    ],
)
def test_wrapper_failure_still_saves_receipt(project, store, executable, arguments, outcome, code):
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forkit_radar.cli",
            "session",
            "run",
            "--project",
            str(project),
            "--tool",
            "other",
            "--store",
            str(store.root),
            "--json",
            "--",
            executable,
            *arguments,
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == code
    assert json.loads(result.stdout)["outcome"] == outcome
    assert len(store.history()) == 1 and not store.active()


def test_incomplete_inventory_never_infers_additions_or_removals():
    a = Snapshot(
        files=(FileState(path="old.py", fingerprint="a" * 64, executable=False),),
        unknown_paths=(),
        excluded_count=0,
        inventory_complete=False,
        reasons=("capture_limit",),
    )
    b = Snapshot(
        files=(FileState(path="new.py", fingerprint="b" * 64, executable=False),),
        unknown_paths=(),
        excluded_count=0,
        inventory_complete=True,
        reasons=(),
    )
    changes, unknown, complete = difference(a, b)
    assert changes == () and unknown == 2 and not complete


def test_oversized_source_is_unknown(project, store):
    with patch("forkit_radar.sessions.inventory.MAX_FILE_BYTES", 8):
        started, snapshot = store.start(project, tool="other")
    assert len(snapshot.unknown_paths) == 2
    receipt = store.finish(started.session_id)
    assert receipt.comparison == "partial" and not receipt.file_changes


@pytest.mark.parametrize("path", ["secrets/helper.py", ".env/config.py", "credentials/provider.js"])
def test_sensitive_directory_scope(path):
    assert not allowed(path)


def test_partial_history_retains_qualifier(project, store):
    started, _ = store.start(project, tool="other")
    store.finish(started.session_id, outcome="recovered")
    result = cli(store, "history")
    assert result.returncode == 0
    assert "at least 0 file changes" in result.stdout and "partial comparison" in result.stdout


def test_wrapper_pwd_matches_explicit_project(project, store):
    program = "import os; from pathlib import Path; assert Path(os.environ['PWD']) == Path.cwd()"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "forkit_radar.cli",
            "session",
            "run",
            "--tool",
            "other",
            "--project",
            str(project),
            "--store",
            str(store.root),
            "--json",
            "--",
            sys.executable,
            "-c",
            program,
        ],
        capture_output=True,
        text=True,
        timeout=15,
    )
    assert result.returncode == 0, result.stderr


def test_finish_failure_rolls_back_receipt_and_state(project, store):
    from forkit_radar.sessions.storage import checked_bytes

    started, _ = store.start(project, tool="other")

    def fail_receipt(model):
        from forkit_radar.sessions.models import Receipt

        if isinstance(model, Receipt):
            raise ContractError("injected_write_failure")
        return checked_bytes(model)

    with (
        patch("forkit_radar.sessions.storage.checked_bytes", side_effect=fail_receipt),
        pytest.raises(ContractError),
    ):
        store.finish(started.session_id)
    assert len(store.active()) == 1 and store.history() == ()
    assert store.finish(started.session_id).status == "completed"


def test_separate_cli_processes_cannot_overlap(project, store):
    commands = [
        sys.executable,
        "-m",
        "forkit_radar.cli",
        "session",
        "start",
        "--project",
        str(project),
        "--tool",
        "other",
        "--store",
        str(store.root),
        "--json",
    ]
    processes = [
        subprocess.Popen(commands, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for _ in range(4)
    ]
    for process in processes:
        process.communicate(timeout=15)
    assert sorted(p.returncode for p in processes) == [0, 2, 2, 2]
    assert len(store.active()) == 1


def test_sigterm_wrapper_closes_interrupted_session(project, store):
    marker = project / "ready.txt"
    program = "from pathlib import Path; import time; Path('main.py').write_text('interrupted edit'); Path('ready.txt').write_text('ready'); time.sleep(30)"
    process = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "forkit_radar.cli",
            "session",
            "run",
            "--project",
            str(project),
            "--tool",
            "other",
            "--store",
            str(store.root),
            "--json",
            "--",
            sys.executable,
            "-c",
            program,
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        deadline = time.monotonic() + 10
        while not marker.exists() and process.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert marker.exists()
        process.send_signal(signal.SIGTERM)
        stdout, stderr = process.communicate(timeout=10)
        assert process.returncode == 143, stderr
        receipt = json.loads(stdout)
        assert receipt["status"] == "interrupted" and receipt["outcome"] == "interrupted"
        assert len(receipt["file_changes"]) == 1 and not store.active()
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)


def test_passive_scan_never_invokes_session_capture():
    from forkit_radar.discovery.scan import scan

    with patch(
        "forkit_radar.sessions.inventory.capture",
        side_effect=AssertionError("session capture invoked"),
    ):
        assert scan(("applications",)).sources
