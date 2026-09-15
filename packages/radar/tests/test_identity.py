"""Core compatibility and adversarial pending-enrollment integration."""

from __future__ import annotations

import hashlib
import json
import os
import selectors
import socket
import sqlite3
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch
from uuid import uuid4

import pytest
from forkit.domain.identity import compute_id
from forkit.domain.integrity import verify_passport_id
from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport
from pydantic import ValidationError

from forkit_radar.contracts import Manifest
from forkit_radar.discovery.scan import scan
from forkit_radar.identity.association import resolve
from forkit_radar.identity.enrollment import EnrollmentEntry, preview, select_source
from forkit_radar.identity.passports import check_bytes, create_bytes, lookup
from forkit_radar.identity.storage import EnrollmentStore, write_new
from forkit_radar.jsonio import ContractError

FIXTURES = Path(__file__).parent / "fixtures"
SECRET = "DO_NOT_EXPORT_f935"


def model_input():
    return {
        "passport_type": "model",
        "name": "test-model",
        "version": "1.0.0",
        "creator": {"name": "Test operator"},
        "task_type": "text-generation",
        "architecture": "transformer",
    }


def core_pair():
    model = ModelPassport.from_dict(model_input())
    agent = AgentPassport(
        name="support-agent",
        version="1.0.0",
        creator={"name": "Test operator"},
        model_id=model.id,
        task_type="customer-support",
        architecture="ReAct",
        temperature=0.7,
    )
    return model, agent


def encode(data):
    return json.dumps(data).encode()


def source(tmp_path, name="agent.json", *, passport_id=None):
    data = json.loads((FIXTURES / "manifest.json").read_bytes())
    data["passport_id"] = passport_id
    data["declared_identity"]["creator"] = {"value": "Test operator", "origin": "declared"}
    path = tmp_path / name
    path.write_bytes(encode(data))
    return path


def selection(path):
    loc, manifest = select_source(agent_file=path)
    return loc, preview(manifest)


def test_real_core_registration_lookup_is_read_only(tmp_path):
    model, agent = core_pair()
    registry = LocalRegistry(tmp_path / "registry")
    registry.register_model(model)
    registry.register_agent(agent)
    files = {
        p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in registry.root.rglob("*")
        if p.is_file()
    }
    for record in (model, agent):
        check = lookup(registry.root, record.id, record.passport_type)
        assert check.status == "consistent" and check.passport_id == record.id
    assert files == {
        p: (hashlib.sha256(p.read_bytes()).hexdigest(), p.stat().st_mtime_ns)
        for p in registry.root.rglob("*")
        if p.is_file()
    }
    missing = tmp_path / "absent"
    assert lookup(missing, agent.id, "agent").status == "missing"
    assert not missing.exists()


@pytest.mark.parametrize("kind", ["model", "agent"])
def test_creation_roundtrips_unchanged_core(kind):
    model, agent = core_pair()
    data = (
        model_input()
        if kind == "model"
        else {
            "passport_type": "agent",
            "name": "support-agent",
            "version": "1.0.0",
            "creator": {"name": "Test operator"},
            "model_id": model.id,
            "task_type": "customer-support",
            "architecture": "ReAct",
        }
    )
    raw = create_bytes(
        encode(data), model_passport=encode(model.to_dict()) if kind == "agent" else None
    )
    value = json.loads(raw)
    assert value["id"] == (model if kind == "model" else agent).id
    cls = ModelPassport if kind == "model" else AgentPassport
    assert cls.from_dict(value).to_dict() == value
    assert check_bytes(raw).status == "consistent"


@pytest.mark.parametrize(
    "change",
    [
        "missing_id",
        "null_id",
        "empty_id",
        "wrong_id",
        "wrong_type",
        "missing_creator",
        "creator_number",
        "empty_creator",
        "name_number",
        "version_number",
        "model_alias",
        "missing_task",
        "bad_architecture",
        "extra",
        "creator_extra",
        "nested_extra",
        "bool_tokens",
        "tool_extra",
        "prompt_extra",
        "null_tools",
    ],
)
def test_core_raw_and_schema_checks_reject_unrepaired_input(change):
    _, agent = core_pair()
    data = agent.to_dict()
    if change == "missing_id":
        data.pop("id")
    elif change == "null_id":
        data["id"] = None
    elif change == "empty_id":
        data["id"] = ""
    elif change == "wrong_id":
        data["id"] = "0" * 64
    elif change == "wrong_type":
        data["passport_type"] = "model"
    elif change == "missing_creator":
        data.pop("creator")
    elif change == "creator_number":
        data["creator"]["name"] = 42
    elif change == "empty_creator":
        data["creator"]["name"] = " "
    elif change == "name_number":
        data["name"] = 42
    elif change == "version_number":
        data["version"] = 1.0
    elif change == "model_alias":
        data["model_id"] = "ollama/alias"
    elif change == "missing_task":
        data.pop("task_type")
    elif change == "bad_architecture":
        data["architecture"] = "guessed-framework"
    elif change == "extra":
        data[SECRET] = "secret"
    elif change == "creator_extra":
        data["creator"][SECRET] = "secret"
    elif change == "nested_extra":
        data["capabilities"][SECRET] = "secret"
    elif change == "tool_extra":
        data["tools"] = [{"name": "tool", "command": SECRET}]
    elif change == "prompt_extra":
        data["system_prompt"] = {"hash": "a" * 64, "length_chars": 12, "prompt": SECRET}
    elif change == "null_tools":
        data["tools"] = None
    else:
        data["max_tokens"] = True
    result = check_bytes(encode(data))
    assert result.status == "invalid"
    assert SECRET not in result.model_dump_json()


def test_missing_id_repair_is_never_used_as_raw_proof():
    _, agent = core_pair()
    data = agent.to_dict()
    data.pop("id")
    assert verify_passport_id(AgentPassport.from_dict(data).to_dict())["valid"]
    with patch.object(
        AgentPassport, "model_validate_json", side_effect=AssertionError("raw check must run first")
    ):
        assert check_bytes(encode(data)).status == "invalid"


@pytest.mark.parametrize(
    "raw",
    [
        b'{"id":1,"id":2}',
        b'{"x":NaN}',
        b'{"x":Infinity}',
        b'{"x":1e999}',
        b'{"x":9007199254740992}',
        b"[]",
        b'{"x":"\xff"}',
        b'{"x":"\\ud800"}',
        b"x" * 65537,
        b'{"x":' + b"[" * 40 + b"0" + b"]" * 40 + b"}",
    ],
)
def test_bounded_core_json(raw):
    assert check_bytes(raw).status == "invalid"


def test_mutable_excluded_metadata_never_becomes_identity_proof():
    _, agent = core_pair()
    data = agent.to_dict()
    data["metadata"] = {"credential": SECRET, "nested": {"private": SECRET}}
    data["memory_config"] = {"private": SECRET}
    result = check_bytes(encode(data))
    assert result.status == "consistent" and SECRET not in result.model_dump_json()
    changed = dict(data, temperature=0.8, tools=[{"name": "new-tool"}], model_id="a" * 64)
    assert verify_passport_id(changed)["valid"]
    assert check_bytes(encode(changed)).status == "consistent"


def test_hash_normalization_cannot_repair_raw_identity():
    _, agent = core_pair()
    data = agent.to_dict()
    data["artifact_hash"] = "A" * 64
    data["id"] = compute_id(
        "agent",
        data["name"],
        data["version"],
        data["creator"]["name"],
        data["creator"]["organization"],
        data["artifact_hash"],
    )
    assert verify_passport_id(data)["valid"]
    assert check_bytes(encode(data)).status == "invalid"


@pytest.mark.parametrize(
    "mutation",
    [
        "missing_model",
        "missing_creator",
        "empty_name",
        "guessed_type",
        "id",
        "prompt",
        "creator_bad_type",
    ],
)
def test_creation_never_invents_required_metadata(mutation):
    model, _ = core_pair()
    data = {
        "passport_type": "agent",
        "name": "test",
        "version": "1.0",
        "creator": {"name": "Test operator"},
        "task_type": "other",
        "architecture": "Custom",
        "model_id": model.id,
    }
    if mutation == "missing_model":
        data.pop("model_id")
    elif mutation == "missing_creator":
        data.pop("creator")
    elif mutation == "empty_name":
        data["name"] = ""
    elif mutation == "guessed_type":
        data["architecture"] = "anything"
    elif mutation == "id":
        data["id"] = "a" * 64
    elif mutation == "creator_bad_type":
        data["creator"] = 12
    else:
        data["system_prompt"] = SECRET
    with pytest.raises(ContractError):
        create_bytes(encode(data), model_passport=encode(model.to_dict()))


def test_agent_creation_requires_a_checked_matching_model():
    model, _ = core_pair()
    data = {
        "passport_type": "agent",
        "name": "test",
        "version": "1.0",
        "creator": {"name": "Test operator"},
        "task_type": "other",
        "architecture": "Custom",
        "model_id": model.id,
    }
    with pytest.raises(ContractError, match="checked_model_passport_required"):
        create_bytes(encode(data))
    bad = model.to_dict()
    bad["id"] = "a" * 64
    with pytest.raises(ContractError, match="checked_model_passport_required"):
        create_bytes(encode(data), model_passport=encode(bad))
    data["model_id"] = "b" * 64
    with pytest.raises(ContractError, match="checked_model_passport_required"):
        create_bytes(encode(data), model_passport=encode(model.to_dict()))


def test_unavailable_core_never_becomes_a_success_or_discloses_errors(monkeypatch):
    import builtins

    model, _ = core_pair()
    raw = encode(model.to_dict())
    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name in {"forkit.domain.integrity", "forkit.schemas"}:
            raise ImportError(SECRET)
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    result = check_bytes(raw)
    assert result.status == "unavailable" and SECRET not in result.model_dump_json()
    with pytest.raises(ContractError, match="core_dependency_unavailable"):
        create_bytes(encode(model_input()))


def test_exact_record_location_and_safe_files(tmp_path):
    model, agent = core_pair()
    root = tmp_path / "registry"
    folder = root / "agents"
    folder.mkdir(parents=True)
    path = folder / f"{agent.id}.json"
    path.write_bytes(encode(model.to_dict()))
    assert lookup(root, agent.id, "agent").status == "invalid"
    path.unlink()
    path.symlink_to(source(tmp_path))
    assert lookup(root, agent.id, "agent").status == "unavailable"
    path.unlink()
    os.mkfifo(path)
    assert lookup(root, agent.id, "agent").status == "unavailable"
    with pytest.raises(ValueError):
        lookup(root, "../escape", "agent")


def test_atomic_creation_never_overwrites(tmp_path):
    raw = create_bytes(encode(model_input()))
    path = tmp_path / "passport.json"
    write_new(path, raw)
    assert path.read_bytes() == raw and path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_new(path, b"replacement")
    assert path.read_bytes() == raw
    link = tmp_path / "link"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        write_new(link, b"replacement")
    assert not list(tmp_path.glob(".radar-*.tmp"))


def test_association_has_no_name_artifact_or_copy_fallback(tmp_path):
    model, agent = core_pair()
    registry = LocalRegistry(tmp_path / "registry")
    registry.register_model(model)
    registry.register_agent(agent)
    _, m = select_source(agent_file=source(tmp_path))
    assert resolve(m, registry.root).state == "unmatched"
    declared = resolve(m, registry.root, selected_ids=(agent.id,))
    assert declared.state == "declared" and declared.model_reference == "consistent"
    assert declared.selected_passport_id == agent.id
    assert declared.candidates[0].status == "consistent"
    assert resolve(m, registry.root, selected_ids=(agent.id, "a" * 64)).state == "ambiguous"
    _, explicit = select_source(agent_file=source(tmp_path, "explicit.json", passport_id=agent.id))
    assert resolve(explicit, registry.root, selected_ids=("a" * 64,)).state == "conflicted"
    raw = explicit.model_dump()
    raw["declared_identity"]["version"]["value"] = "2.0.0"
    assert resolve(Manifest.model_validate(raw), registry.root).state == "conflicted"
    assert resolve(explicit).state == "declared"
    (registry.models_dir / f"{model.id}.json").unlink()
    assert resolve(explicit, registry.root).model_reference == "missing"


def test_selected_graph_requires_exact_key_and_never_imports(tmp_path):
    (tmp_path / "langgraph.json").write_text(
        json.dumps({"graphs": {SECRET: "agent.py:graph", "second": "other.py:graph"}})
    )
    (tmp_path / "agent.py").write_text('raise RuntimeError("must not run")')
    with pytest.raises(ContractError):
        select_source(project=tmp_path)
    loc, m = select_source(project=tmp_path, graph_key=SECRET)
    assert m.declared_identity.name.value is None and SECRET not in m.model_dump_json()
    store = EnrollmentStore(tmp_path / "private")
    entry = store.propose(loc, preview(m))
    assert SECRET not in entry.model_dump_json() and str(tmp_path) not in entry.model_dump_json()
    with sqlite3.connect(store.root / "enrollment.sqlite3") as db:
        assert SECRET in db.execute("SELECT locator FROM sources").fetchone()[0].decode()


def test_pending_clone_and_cancel_state_machine(tmp_path):
    original = source(tmp_path)
    clone = tmp_path / "clone.json"
    clone.write_bytes(original.read_bytes())
    store = EnrollmentStore(tmp_path / "private")
    a = store.propose(*selection(original))
    b = store.propose(*selection(clone))
    assert a.draft.reserved_logical_agent_id != b.draft.reserved_logical_agent_id
    assert a.draft.source_slot_id != b.draft.source_slot_id
    assert a.state == b.state == "pending"
    assert a.draft.authority_id is None and a.draft.accepted_binding_digest is None
    assert a.draft.preview.manifest.logical_agent_id is None
    with pytest.raises(ContractError, match="pending_proposal_exists"):
        store.propose(*selection(original))
    assert len(EnrollmentStore(store.root).list()) == 2
    assert store.cancel(a.draft.proposal_id).draft == a.draft
    with pytest.raises(ContractError, match="already_cancelled"):
        store.cancel(a.draft.proposal_id)
    new = store.propose(*selection(original))
    assert new.draft.reserved_logical_agent_id != a.draft.reserved_logical_agent_id
    assert store.root.stat().st_mode & 0o777 == 0o700
    assert (store.root / "enrollment.sqlite3").stat().st_mode & 0o777 == 0o600
    with sqlite3.connect(store.root / "enrollment.sqlite3") as db:
        assert db.execute("SELECT COUNT(*) FROM draft_events").fetchone()[0] == 4


def test_copied_logical_id_does_not_enroll(tmp_path):
    path = source(tmp_path)
    raw = json.loads(path.read_text())
    claimed = str(uuid4())
    raw["logical_agent_id"] = claimed
    raw["provisional_component_key"] = None
    path.write_bytes(encode(raw))
    store = EnrollmentStore(tmp_path / "private")
    entry = store.propose(*selection(path))
    assert entry.draft.reserved_logical_agent_id != claimed
    assert claimed not in entry.model_dump_json()


def test_preview_and_missing_store_operations_write_nothing(tmp_path):
    path = source(tmp_path)
    loc, view = selection(path)
    assert view.authority == "unavailable"
    root = tmp_path / "private"
    store = EnrollmentStore(root)
    for operation in (
        store.list,
        lambda: store.get(str(uuid4())),
        lambda: store.cancel(str(uuid4())),
    ):
        with pytest.raises(OSError):
            operation()
        assert not root.exists()
    path.write_bytes(b"{}")
    with pytest.raises(ContractError):
        store.propose(loc, view)
    assert not root.exists()


def test_source_change_and_conflict_do_not_store_a_draft(tmp_path):
    path = source(tmp_path)
    loc, view = selection(path)
    raw = json.loads(path.read_text())
    raw["declared_identity"]["name"]["value"] = "changed"
    path.write_bytes(encode(raw))
    store = EnrollmentStore(tmp_path / "private")
    with pytest.raises(ContractError, match="source_changed"):
        store.propose(loc, view)
    assert not store.root.exists()
    loc, m = select_source(agent_file=path)
    unresolved = preview(m, passport_ids=("a" * 64, "b" * 64))
    with pytest.raises(ContractError, match="resolve_association"):
        store.propose(loc, unresolved)
    assert not store.root.exists()


@pytest.mark.parametrize(
    "target",
    [
        "directory_mode",
        "file_mode",
        "symlink_file",
        "hardlink_file",
        "symlink_root",
        "journal_symlink",
    ],
)
def test_store_rejects_unsafe_permissions_and_links(tmp_path, target):
    path = source(tmp_path)
    store = EnrollmentStore(tmp_path / "private")
    store.propose(*selection(path))
    db = store.root / "enrollment.sqlite3"
    if target == "directory_mode":
        store.root.chmod(0o755)
    elif target == "file_mode":
        db.chmod(0o644)
    elif target == "symlink_file":
        moved = tmp_path / "moved"
        db.rename(moved)
        db.symlink_to(moved)
    elif target == "hardlink_file":
        os.link(db, tmp_path / "linked")
    elif target == "symlink_root":
        moved = tmp_path / "moved"
        store.root.rename(moved)
        store.root.symlink_to(moved, target_is_directory=True)
    else:
        (store.root / "enrollment.sqlite3-journal").symlink_to(path)
    with pytest.raises((OSError, ValueError)):
        store.list()


@pytest.mark.parametrize("mutation", ["version", "trigger", "payload", "state", "schema"])
def test_corrupted_or_forged_store_is_not_trusted(tmp_path, mutation):
    store = EnrollmentStore(tmp_path / "private")
    entry = store.propose(*selection(source(tmp_path)))
    with sqlite3.connect(store.root / "enrollment.sqlite3") as db:
        if mutation == "version":
            db.execute("PRAGMA user_version=99")
        elif mutation == "trigger":
            db.execute(
                "CREATE TRIGGER surprise AFTER INSERT ON drafts BEGIN DELETE FROM drafts; END"
            )
        elif mutation == "schema":
            db.execute("CREATE TABLE unknown(x)")
        elif mutation == "state":
            db.execute("PRAGMA ignore_check_constraints=ON")
            db.execute("UPDATE drafts SET state='enrolled'")
        else:
            raw = entry.draft.model_dump(mode="json")
            raw["authority_id"] = str(uuid4())
            db.execute("UPDATE drafts SET payload=?", (encode(raw),))
    with pytest.raises(ValueError):
        store.list()


def test_real_sqlite_concurrent_writers_and_rollback(tmp_path):
    paths = [source(tmp_path, f"agent-{i}.json") for i in range(12)]
    store = EnrollmentStore(tmp_path / "private")
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda p: store.propose(*selection(p)), paths))
    assert len({r.draft.reserved_logical_agent_id for r in results}) == 12
    assert len(store.list()) == 12
    with pytest.raises(RuntimeError), store._connect(write=True) as db:
        db.execute("UPDATE drafts SET state='cancelled'")
        raise RuntimeError("injected_failure")
    assert all(e.state == "pending" for e in store.list())


def test_local_locator_keys_are_not_authorities_or_global_ids(tmp_path):
    path = source(tmp_path)
    first = EnrollmentStore(tmp_path / "first")
    second = EnrollmentStore(tmp_path / "second")
    first.propose(*selection(path))
    second.propose(*selection(path))
    tokens = []
    for store in (first, second):
        with sqlite3.connect(store.root / "enrollment.sqlite3") as db:
            tokens.append(db.execute("SELECT locator_token FROM sources").fetchone()[0])
            assert (
                len(db.execute("SELECT value FROM settings WHERE name='locator_key'").fetchone()[0])
                == 32
            )
        assert store.list()[0].draft.authority_id is None
    assert tokens[0] != tokens[1]


def test_no_forged_enrollment_entry_can_claim_authority(tmp_path):
    entry = EnrollmentStore(tmp_path / "private").propose(*selection(source(tmp_path)))
    raw = entry.model_dump(mode="json")
    raw["state"] = "enrolled"
    with pytest.raises(ValidationError):
        EnrollmentEntry.model_validate(raw)


def test_identity_operations_do_not_connect_or_execute(tmp_path, monkeypatch):
    path = source(tmp_path)
    loc, view = selection(path)

    def forbidden(*a, **kw):
        raise AssertionError("network_or_execution")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    assert check_bytes(create_bytes(encode(model_input()))).status == "consistent"
    assert EnrollmentStore(tmp_path / "private").propose(loc, view).state == "pending"


def test_installed_cli_preview_save_restart_cancel_and_passport(tmp_path):
    path = source(tmp_path)
    store = tmp_path / "private"
    command = [sys.executable, "-I", "-m", "forkit_radar.cli"]

    def run(*args):
        return subprocess.run([*command, *map(str, args)], capture_output=True, cwd="/", timeout=10)

    args = ("enroll", "--agent-manifest", path, "--store", store, "--json")
    initial = run(*args)
    assert initial.returncode == 0 and not store.exists()
    result = run(*args, "--save-pending")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    identifier = data["draft"]["proposal_id"]
    assert str(tmp_path).encode() not in result.stdout
    assert data["state"] == "pending" and data["draft"]["authority_id"] is None
    assert run("enrollment", "inspect", identifier, "--store", store).returncode == 0
    assert run("enrollment", "cancel", identifier, "--store", store).returncode == 0
    assert (
        json.loads(run("enrollment", "list", "--store", store, "--json").stdout)[0]["state"]
        == "cancelled"
    )
    input_path = tmp_path / "input.json"
    input_path.write_bytes(encode(model_input()))
    output = tmp_path / "created.json"
    assert run("passport", "create", "--input", input_path).returncode == 0 and not output.exists()
    assert run("passport", "create", "--input", input_path, "--output", output).returncode == 0
    assert run("passport", "inspect", "--file", output).returncode == 0
    result = run("passport", "create", "--input", input_path, "--output", output)
    assert result.returncode == 2 and str(tmp_path).encode() not in result.stderr


def test_scan_core_checks_remain_declared_not_enrolled(tmp_path):
    model, agent = core_pair()
    registry = LocalRegistry(tmp_path / "registry")
    registry.register_model(model)
    registry.register_agent(agent)
    path = source(tmp_path, passport_id=agent.id)
    report = scan(("agent-manifest",), agent_file=path, registry=registry.root)
    found = report.sources[0].findings[0]
    assert found.evidence.passport == "consistent" and found.evidence.association == "declared"
    assert found.evidence.runtime == "not_observed" and found.evidence.acceptance == "unreviewed"
    assert found.observation.manifest.logical_agent_id is None
    assert report.storage == "not_saved"


def test_separate_process_writers_preserve_distinct_drafts(tmp_path):
    store = tmp_path / "private"
    paths = [source(tmp_path, f"process-{i}.json") for i in range(4)]
    children = []
    try:
        for path in paths:
            children.append(
                subprocess.Popen(
                    [
                        sys.executable,
                        "-I",
                        "-m",
                        "forkit_radar.cli",
                        "enroll",
                        "--agent-manifest",
                        str(path),
                        "--store",
                        str(store),
                        "--save-pending",
                        "--json",
                    ],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    cwd="/",
                )
            )
        for child in children:
            stdout, stderr = child.communicate(timeout=10)
            assert child.returncode == 0, stderr
            assert json.loads(stdout)["state"] == "pending"
        entries = EnrollmentStore(store).list()
        assert len(entries) == 4
        assert len({e.draft.reserved_logical_agent_id for e in entries}) == 4
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)


def test_killed_writer_rolls_back_without_losing_committed_proposal(tmp_path):
    store = EnrollmentStore(tmp_path / "private")
    original = store.propose(*selection(source(tmp_path)))
    script = """
import sys,time
from pathlib import Path
from forkit_radar.identity.storage import EnrollmentStore
with EnrollmentStore(Path(sys.argv[1]))._connect(write=True) as db:
    db.execute("UPDATE drafts SET state='cancelled'")
    print('ready',flush=True)
    time.sleep(30)
"""
    child = subprocess.Popen(
        [sys.executable, "-I", "-c", script, str(store.root)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        cwd="/",
    )
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(child.stdout, selectors.EVENT_READ)
            assert selector.select(timeout=5), "transaction never started"
            assert child.stdout.readline() == b"ready\n"
        child.kill()
        child.wait(timeout=3)
    finally:
        if child.poll() is None:
            child.kill()
        child.wait(timeout=3)
        child.stdout.close()
    # A writer lets SQLite recover its journal. Never delete recovery sidecars.
    store.propose(*selection(source(tmp_path, "second.json")))
    assert store.get(original.draft.proposal_id).state == "pending"
    assert len(store.list()) == 2
