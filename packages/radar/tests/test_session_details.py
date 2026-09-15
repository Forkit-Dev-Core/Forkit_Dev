"""Real project/registry receipts, conservative metadata and immutable v1 history."""

from __future__ import annotations

import json
import sqlite3
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest
from forkit.registry.local import LocalRegistry
from forkit.schemas import AgentPassport, ModelPassport

from forkit_radar.identity.storage import canonical
from forkit_radar.sessions.cli import render
from forkit_radar.sessions.dependencies import npm_range
from forkit_radar.sessions.details import ReceiptV2, Selection
from forkit_radar.sessions.metadata import capture
from forkit_radar.sessions.models import Receipt
from forkit_radar.sessions.storage import SessionStore, read_receipt, read_snapshot

SECRET = "DO_NOT_STORE_CREDENTIAL_883cca"
FIXTURES = Path(__file__).parent / "fixtures"


def write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


@pytest.fixture
def project(tmp_path):
    path = tmp_path / "project"
    path.mkdir()
    subprocess.run(["/usr/bin/git", "init", "-q", str(path)], check=True, capture_output=True)
    (path / "main.py").write_text("print('baseline')\n")
    return path


@pytest.fixture
def store(tmp_path):
    return SessionStore(tmp_path / "private")


def stop(store, project, *, selection=None):
    started, _ = store.start(project, tool="codex", selection=selection)
    return store.finish(started.session_id)


def changes(receipt, source):
    return [c for c in receipt.metadata.changes if c.source == source]


def source(metadata, key):
    return next(s for s in metadata.sources if s.key == key)


def core_registry(tmp_path):
    model = ModelPassport(
        name="base-model",
        version="1.0",
        creator={"name": "Fixture"},
        task_type="text-generation",
        architecture="transformer",
    )
    agent = AgentPassport(
        name="support-agent",
        version="1.0.0",
        creator={"name": "Fixture"},
        model_id=model.id,
        task_type="customer-support",
        architecture="ReAct",
    )
    registry = LocalRegistry(tmp_path / "registry")
    registry.register_model(model)
    registry.register_agent(agent)
    return registry, model, agent


def agent_manifest(path, *, passport_id=None):
    data = json.loads((FIXTURES / "manifest.json").read_text())
    data["passport_id"] = passport_id
    data["declared_identity"]["creator"] = {"value": "Fixture", "origin": "declared"}
    data["models"] = []
    data["measurement_completeness"]["models"] = "complete"
    write(path, data)
    return data


def test_npm_add_remove_and_version_change_are_declared(project, store):
    write(project / "package.json", {"dependencies": {"stripe": "^1.0.0", "old": "2.0.0"}})
    started, _ = store.start(project, tool="cursor")
    write(
        project / "package.json",
        {"dependencies": {"stripe": "^2.0.0"}, "devDependencies": {"playwright": "1.58.0"}},
    )
    receipt = store.finish(started.session_id)
    assert {(c.label, c.kind, c.before, c.after) for c in changes(receipt, "npm-manifest")} == {
        ("stripe", "changed", "^1.0.0", "^2.0.0"),
        ("old", "removed", "2.0.0", None),
        ("playwright", "added", None, "1.58.0"),
    }
    assert receipt.dependency_comparison == "complete"
    assert receipt.meaningful_categories == ("files", "dependencies")
    assert "playwright" in render(receipt) and "declared metadata" in render(receipt)
    assert receipt.passport_id is None and receipt.runtime_observation == "not_observed"
    assert read_receipt(canonical(receipt)) == receipt


@pytest.mark.parametrize(
    "spec", ["^1.2.3", "~2.1", ">= 1.0 < 2", "1.0 - 2.0", "1 || 2", "1.2.3-beta.2", "*", "latest"]
)
def test_supported_npm_constraints(spec):
    assert npm_range(spec)


@pytest.mark.parametrize(
    "spec",
    [
        "https://user:password@example.invalid/a",
        "file:../private",
        "npm:other@1.0",
        "workspace:*",
        "git+ssh://private",
        "^not-a-version",
        "<",
        "1 ||",
        "",
        "${TOKEN}",
    ],
)
def test_unsupported_npm_specs_abstain(spec):
    with pytest.raises(ValueError):
        npm_range(spec)


@pytest.mark.parametrize(
    "replacement",
    [
        "{broken",
        '{"dependencies": []}',
        '{"dependencies": {"stripe": "https://user:secret@example.invalid"}}',
        '{"dependencies": {"stripe": "1", "stripe": "2"}}',
        '{"workspaces": ["packages/*"]}',
    ],
)
def test_partial_dependency_sources_never_create_false_removals(project, store, replacement):
    write(project / "package.json", {"dependencies": {"stripe": "1.0.0"}})
    started, _ = store.start(project, tool="other")
    (project / "package.json").write_text(replacement)
    receipt = store.finish(started.session_id)
    assert receipt.dependency_comparison == "partial"
    assert not changes(receipt, "npm-manifest")
    assert "unknown, not removals" in render(receipt)


def test_missing_manifest_is_known_absence(project, store):
    write(project / "package.json", {"dependencies": {"stripe": "1.0.0"}})
    started, _ = store.start(project, tool="other")
    (project / "package.json").unlink()
    receipt = store.finish(started.session_id)
    assert [(c.kind, c.label) for c in changes(receipt, "npm-manifest")] == [("removed", "stripe")]


@pytest.mark.parametrize("unsafe", ["symlink", "hardlink", "fifo", "oversized", "denied"])
def test_unsafe_metadata_is_unknown_without_false_removal(project, store, tmp_path, unsafe):
    write(project / "package.json", {"dependencies": {"stripe": "1.0.0"}})
    started, _ = store.start(project, tool="other")
    original = project / "package.json"
    original.unlink()
    if unsafe == "symlink":
        original.symlink_to(tmp_path / "missing")
    elif unsafe == "hardlink":
        external = tmp_path / "other.json"
        write(external, {})
        original.hardlink_to(external)
    elif unsafe == "fifo":
        import os

        os.mkfifo(original)
    elif unsafe == "oversized":
        original.write_bytes(b" " * 1_048_577)
    else:
        write(original, {})
        original.chmod(0)
    try:
        receipt = store.finish(started.session_id)
    finally:
        if unsafe == "denied":
            original.chmod(0o600)
    assert not changes(receipt, "npm-manifest")
    assert receipt.dependency_comparison == "partial"


def test_npm_lock_versions_transitives_and_slots(project, store):
    data = {
        "lockfileVersion": 3,
        "packages": {
            "": {},
            "node_modules/a": {
                "version": "1.0.0",
                "resolved": f"https://user:{SECRET}@example.invalid/a",
            },
            "node_modules/a/node_modules/b": {"version": "1.2.3"},
        },
    }
    write(project / "package-lock.json", data)
    started, _ = store.start(project, tool="other")
    data["packages"]["node_modules/a"]["version"] = "2.0.0"
    del data["packages"]["node_modules/a/node_modules/b"]
    data["packages"]["node_modules/b"] = {"version": "1.2.3"}
    write(project / "package-lock.json", data)
    receipt = store.finish(started.session_id)
    assert {c.kind for c in changes(receipt, "npm-lock")} == {"added", "removed", "changed"}
    assert SECRET.encode() not in (store.root / store.database_name).read_bytes()
    assert all("resolved" not in c.model_dump_json() for c in receipt.metadata.changes)


@pytest.mark.parametrize("lockfile_version", [1, 4, "3", True])
def test_unsupported_lock_versions_remain_unknown(project, lockfile_version):
    write(project / "package-lock.json", {"lockfileVersion": lockfile_version, "packages": {}})
    assert source(capture(project, Selection(), b"k" * 32), "npm-lock").state == "unavailable"


def test_formatting_reordering_and_unrelated_settings_do_not_count(project, store):
    write(
        project / "package.json",
        {"dependencies": {"a": "1.0", "b": "2.0"}, "scripts": {"test": "dangerous-command"}},
    )
    started, _ = store.start(project, tool="other")
    (project / "package.json").write_text(
        '{"scripts": {"test":"other-command"}, "dependencies": {"b":"2.0","a":"1.0"}}'
    )
    receipt = store.finish(started.session_id)
    assert receipt.file_changes and not receipt.metadata.changes


def test_python_specifiers_extras_and_markers_stay_local(project, store):
    (project / "pyproject.toml").write_text(
        '[project]\ndependencies=["requests>=2,<3", "httpx[http2]>=0.27; python_version < \'3.12\'"]\n[project.optional-dependencies]\ntest=["pytest>=8"]\n'
    )
    (project / "requirements.txt").write_text(
        f"flask==3.0 # comment\nrich>=13; os_name == '{SECRET}'\n"
    )
    started, _ = store.start(project, tool="other")
    (project / "pyproject.toml").write_text(
        '[project]\ndependencies=["requests>=3", "httpx[http2]>=0.27; python_version < \'3.12\'"]\n[project.optional-dependencies]\ntest=["pytest>=8"]\n'
    )
    (project / "requirements.txt").write_text(f"flask==3.1\nrich>=13; os_name == '{SECRET}'\n")
    receipt = store.finish(started.session_id)
    assert {(c.label, c.kind) for c in receipt.metadata.changes} == {
        ("requests", "changed"),
        ("flask", "changed"),
    }
    assert SECRET.encode() not in (store.root / store.database_name).read_bytes()


def test_python_dynamic_urls_includes_and_duplicates_abstain(project, store):
    (project / "requirements.txt").write_text("requests==2.0\n")
    started, _ = store.start(project, tool="other")
    (project / "requirements.txt").write_text(
        f"-r {SECRET}\nrequests @ https://user:{SECRET}@example.invalid/x\n"
    )
    (project / "pyproject.toml").write_text('[project]\ndynamic=["dependencies"]\n')
    receipt = store.finish(started.session_id)
    assert not changes(receipt, "python-requirements")
    assert receipt.dependency_comparison == "partial"
    assert SECRET.encode() not in (store.root / store.database_name).read_bytes()
    (project / "requirements.txt").write_text("requests==2\nrequests==3\n")
    assert (
        source(capture(project, Selection(), b"k" * 32), "python-requirements").state
        == "unavailable"
    )


def test_known_unsupported_formats_are_visible(project, store):
    (project / "pnpm-lock.yaml").write_text("lockfileVersion: '9.0'")
    receipt = stop(store, project)
    assert receipt.dependency_comparison == "partial"
    assert any(
        c.source == "other-dependencies" and c.after == "unsupported"
        for c in receipt.metadata.coverage
    )


def test_mcp_names_are_pseudonymous_and_reordering_stable(project, store):
    config = project / ".cursor/mcp.json"
    write(
        config,
        {
            "mcpServers": {
                SECRET: {"command": "never-execute", "args": [SECRET]},
                "playwright": {"command": "npx", "env": {"TOKEN": SECRET}},
            }
        },
    )
    started, _ = store.start(project, tool="cursor")
    write(
        config,
        {
            "mcpServers": {
                "playwright": {"command": "npx", "env": {"TOKEN": "changed"}},
                SECRET: {"command": "never-execute", "args": ["changed"]},
            }
        },
    )
    receipt = store.finish(started.session_id)
    assert not changes(receipt, "cursor-project-mcp")
    assert SECRET.encode() not in (store.root / store.database_name).read_bytes()
    assert "never-execute" not in receipt.model_dump_json()


def test_mcp_equal_count_replacements_are_detected(project, store):
    config = project / ".mcp.json"
    write(config, {"mcpServers": {"old": {"command": "do-not-run"}}})
    started, _ = store.start(project, tool="claude-code")
    write(
        config,
        {
            "mcpServers": {
                "playwright": {"type": "http", "url": f"https://user:{SECRET}@example.invalid"}
            }
        },
    )
    receipt = store.finish(started.session_id)
    assert {c.kind for c in changes(receipt, "claude-project-mcp")} == {"added", "removed"}
    assert "playwright (MCP declaration)" in render(receipt)
    assert SECRET.encode() not in (store.root / store.database_name).read_bytes()


@pytest.mark.parametrize("adapter", ["codex", "cursor", "claude"])
def test_unreadable_mcp_is_not_removed(project, store, adapter):
    path = (
        project
        / {"codex": ".codex/config.toml", "cursor": ".cursor/mcp.json", "claude": ".mcp.json"}[
            adapter
        ]
    )
    if adapter == "codex":
        path.parent.mkdir()
        path.write_text('[mcp_servers.playwright]\ncommand="npx"\n')
    else:
        write(path, {"mcpServers": {"playwright": {"command": "npx"}}})
    started, _ = store.start(project, tool="other")
    path.write_text("broken!]")
    receipt = store.finish(started.session_id)
    assert not changes(receipt, f"{adapter}-project-mcp")
    assert receipt.configuration_comparison == "partial"


def test_codex_activation_models_and_unknown_model_not_removal(project, store):
    path = project / ".codex/config.toml"
    path.parent.mkdir()
    path.write_text('model="model-a"\n[mcp_servers.playwright]\ncommand="npx"\nenabled=true\n')
    started, _ = store.start(project, tool="codex")
    path.write_text('model="model-b"\n[mcp_servers.playwright]\ncommand="npx"\nenabled=false\n')
    receipt = store.finish(started.session_id)
    assert [(c.before, c.after) for c in changes(receipt, "codex-project-model")] == [
        ("model-a", "model-b")
    ]
    assert len(changes(receipt, "codex-project-mcp")) == 1
    started, _ = store.start(project, tool="codex")
    path.write_text(f'model="https://user:{SECRET}@example.invalid"\n[mcp_servers.playwright]\n')
    bad = store.finish(started.session_id)
    assert not changes(bad, "codex-project-model") and not changes(bad, "codex-project-mcp")
    assert bad.configuration_comparison == "partial"
    assert SECRET.encode() not in (store.root / store.database_name).read_bytes()


def test_explicit_manifest_tools_settings_and_models_reuse_adapter(project, store, tmp_path):
    path = tmp_path / "agent.json"
    data = agent_manifest(path)
    selected = Selection(agent_manifest=str(path))
    started, _ = store.start(project, tool="codex", selection=selected)
    data["settings"]["max_tokens"] = 1024
    data["tools"] = [
        {
            "key": "playwright",
            "name": {"origin": "declared", "value": "playwright"},
            "origin": "declared",
            "transport": "stdio",
            "permissions": ["read_files"],
        }
    ]
    data["models"] = [
        {
            "key": "main",
            "origin": "declared",
            "name": {"origin": "declared", "value": "local-model"},
            "version": {"origin": "declared", "value": "1.0"},
            "provider": {"origin": "declared", "value": "local"},
            "passport_id": None,
            "digest": {"origin": "unknown", "value": None},
        }
    ]
    write(path, data)
    receipt = store.finish(started.session_id)
    assert {c.category for c in receipt.metadata.changes} == {"tools", "models", "configuration"}
    assert receipt.passport_after.state == "not_selected"


def test_raw_valid_passport_explicit_association_no_registry_mutation(project, store, tmp_path):
    registry, model, agent = core_registry(tmp_path)
    original = {p: p.read_bytes() for p in registry.root.rglob("*") if p.is_file()}
    receipt = stop(
        store, project, selection=Selection(registry=str(registry.root), passport_id=agent.id)
    )
    assert receipt.passport_after.state == "consistent" and receipt.passport_id == agent.id
    assert receipt.passport_after.model_reference == "consistent"
    assert receipt.tool == "codex" and receipt.passport_after.name == "support-agent"
    assert "association declared by you" in render(receipt)
    assert original == {p: p.read_bytes() for p in registry.root.rglob("*") if p.is_file()}
    assert receipt.passport_after.model_id == model.id


def test_no_automatic_passport_attachment_by_name_or_registry(project, store, tmp_path):
    registry, _, _ = core_registry(tmp_path)
    path = tmp_path / "agent.json"
    agent_manifest(path)
    receipt = stop(
        store, project, selection=Selection(agent_manifest=str(path), registry=str(registry.root))
    )
    assert receipt.passport_id is None and receipt.passport_after.state == "not_selected"


def test_conflicting_passport_selection_never_picks_one(project, store, tmp_path):
    registry, model, agent = core_registry(tmp_path)
    second = AgentPassport(
        name="second-agent",
        version="1.0",
        creator={"name": "Fixture"},
        model_id=model.id,
        task_type="customer-support",
        architecture="ReAct",
    )
    registry.register_agent(second)
    path = tmp_path / "agent.json"
    agent_manifest(path, passport_id=agent.id)
    receipt = stop(
        store,
        project,
        selection=Selection(
            agent_manifest=str(path), registry=str(registry.root), passport_id=second.id
        ),
    )
    assert receipt.passport_id is None and receipt.passport_after.state == "conflicted"
    assert receipt.passport_after.reason == "multiple_explicit_references"


@pytest.mark.parametrize(
    "failure",
    [
        "missing_id",
        "changed_name",
        "model_missing",
        "model_invalid",
        "registry_missing",
        "manifest_missing",
    ],
)
def test_passport_failures_are_visible_without_repair(project, store, tmp_path, failure):
    registry, model, agent = core_registry(tmp_path)
    selected = Selection(registry=str(registry.root), passport_id=agent.id)
    agent_path = registry.root / "agents" / f"{agent.id}.json"
    model_path = registry.root / "models" / f"{model.id}.json"
    if failure in {"missing_id", "changed_name"}:
        data = json.loads(agent_path.read_text())
        if failure == "missing_id":
            del data["id"]
        else:
            data["name"] = "tampered"
        write(agent_path, data)
    elif failure == "model_missing":
        model_path.unlink()
    elif failure == "model_invalid":
        write(model_path, {})
    elif failure == "registry_missing":
        selected = Selection(registry=str(tmp_path / "does-not-exist"), passport_id=agent.id)
    else:
        selected = Selection(
            registry=str(registry.root),
            passport_id=agent.id,
            agent_manifest=str(tmp_path / "missing-agent.json"),
        )
    original = {p: p.read_bytes() for p in registry.root.rglob("*") if p.is_file()}
    receipt = stop(store, project, selection=selected)
    if failure == "model_missing":
        assert (
            receipt.passport_id == agent.id and receipt.passport_after.model_reference == "missing"
        )
    else:
        assert receipt.passport_id is None and receipt.passport_after.state in {
            "conflicted",
            "unavailable",
        }
    assert original == {p: p.read_bytes() for p in registry.root.rglob("*") if p.is_file()}
    assert not (tmp_path / "does-not-exist").exists()


def test_passport_version_transition_is_declared_not_lineage(project, store, tmp_path):
    registry, model, old = core_registry(tmp_path)
    new = AgentPassport(
        name="support-agent",
        version="2.0.0",
        creator={"name": "Fixture"},
        model_id=model.id,
        task_type="customer-support",
        architecture="ReAct",
    )
    registry.register_agent(new)
    path = tmp_path / "agent.json"
    data = agent_manifest(path, passport_id=old.id)
    selected = Selection(registry=str(registry.root), agent_manifest=str(path))
    started, _ = store.start(project, tool="codex", selection=selected)
    data["passport_id"] = new.id
    data["declared_identity"]["version"]["value"] = "2.0.0"
    write(path, data)
    receipt = store.finish(started.session_id)
    assert receipt.metadata.passport_change == "changed" and receipt.passport_id == new.id
    assert "1.0.0 → 2.0.0; lineage not inferred" in render(receipt)


def test_previous_and_between_sessions_are_separate(project, store):
    first = stop(store, project)
    (project / "between.py").write_text("between sessions")
    write(project / "package.json", {"dependencies": {"stripe": "1.0"}})
    started, _ = store.start(project, tool="cursor")
    (project / "during.py").write_text("during session")
    write(project / "package.json", {"dependencies": {"stripe": "2.0"}})
    current = store.finish(started.session_id)
    assert current.since_previous.baseline_session_id == first.session_id
    assert {c.path for c in current.between_sessions.file_changes} == {"between.py", "package.json"}
    assert {c.path for c in current.file_changes} == {"during.py", "package.json"}
    assert {c.path for c in current.since_previous.file_changes} == {
        "during.py",
        "between.py",
        "package.json",
    }
    assert current.between_sessions.metadata.changes[0].kind == "added"
    assert current.metadata.changes[0].kind == "changed"
    assert store.history()[0] == current


def test_complete_baseline_preferred_over_newer_partial(project, store):
    write(project / "package.json", {"dependencies": {"stripe": "1.0"}})
    first = stop(store, project)
    started, _ = store.start(project, tool="codex")
    (project / "package.json").write_text("broken")
    partial = store.finish(started.session_id)
    write(project / "package.json", {"dependencies": {"stripe": "2.0"}})
    current = stop(store, project)
    assert current.previous_session_id == partial.session_id
    assert current.since_previous.baseline_session_id == first.session_id
    assert current.since_previous.skipped_sessions == 1
    assert current.since_previous.metadata.changes[0].kind == "changed"
    assert current.metadata.changes == ()


def test_selection_scope_change_has_no_fake_previous_diff(project, store, tmp_path):
    stop(store, project)
    path = tmp_path / "agent.json"
    agent_manifest(path)
    current = stop(store, project, selection=Selection(agent_manifest=str(path)))
    assert current.previous_session_id is not None
    assert current.since_previous.comparison == "no_baseline"


def test_recovery_is_not_a_normal_baseline(project, store):
    started, _ = store.start(project, tool="other")
    store.finish(started.session_id, outcome="recovered")
    current = stop(store, project)
    assert current.since_previous.comparison == "no_baseline"


def test_old_receipts_and_active_sessions_stay_readable_and_immutable(project, store):
    # Recreate the exact v1 payload shapes without defaults from the new schema.
    first = stop(store, project)
    old = Receipt.model_validate(
        {k: v for k, v in first.model_dump().items() if k in Receipt.model_fields}
        | {
            "schema_version": "1.0",
            "passport_id": None,
            "dependency_comparison": "not_available",
            "configuration_comparison": "not_available",
        }
    )
    raw = canonical(old)
    with sqlite3.connect(store.root / store.database_name) as db:
        db.execute("UPDATE receipts SET payload=? WHERE session_id=?", (raw, first.session_id))
        rows = db.execute(
            "SELECT phase,payload FROM snapshots WHERE session_id=?", (first.session_id,)
        ).fetchall()
        for phase, payload in rows:
            files, _ = read_snapshot(payload)
            db.execute(
                "UPDATE snapshots SET payload=? WHERE session_id=? AND phase=?",
                (canonical(files), first.session_id, phase),
            )
    assert store.receipt(first.session_id) == old
    assert "Legacy receipt" in render(old) and "declared metadata" not in render(old)
    active, _ = store.start(project, tool="other")
    with sqlite3.connect(store.root / store.database_name) as db:
        payload = db.execute(
            "SELECT payload FROM snapshots WHERE session_id=?", (active.session_id,)
        ).fetchone()[0]
        files, _ = read_snapshot(payload)
        db.execute(
            "UPDATE snapshots SET payload=? WHERE session_id=?",
            (canonical(files), active.session_id),
        )
    finished = store.finish(active.session_id)
    assert type(finished) is Receipt and finished.schema_version == "1.0"
    current = stop(store, project)
    assert current.since_previous.comparison == "no_baseline"
    assert len(store.history()) == 3
    with sqlite3.connect(store.root / store.database_name) as db:
        assert (
            db.execute(
                "SELECT payload FROM receipts WHERE session_id=?", (first.session_id,)
            ).fetchone()[0]
            == raw
        )
        assert db.execute("PRAGMA user_version").fetchone()[0] == 2


def test_default_capture_never_reads_home_or_executes_mcp(project, store, tmp_path):
    import os

    sentinel = tmp_path / "executed"
    write(
        project / ".mcp.json",
        {
            "mcpServers": {
                "malicious": {
                    "command": sys.executable,
                    "args": ["-c", f"open({str(sentinel)!r}, 'w').write('bad')"],
                }
            }
        },
    )
    original_open = os.open

    def guarded_open(path, *args, **kwargs):
        assert path != "uncaptured-home", "implicit home file read"
        return original_open(path, *args, **kwargs)

    with (
        patch("pathlib.Path.home", return_value=tmp_path / "uncaptured-home"),
        patch("os.open", side_effect=guarded_open),
        patch("socket.socket", side_effect=AssertionError("network access")),
    ):
        receipt = stop(store, project)
    assert not sentinel.exists() and receipt.configuration_comparison == "complete"


def test_local_cli_explicit_association_json(project, store, tmp_path):
    registry, _, agent = core_registry(tmp_path)
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
            "--registry",
            str(registry.root),
            "--passport-id",
            agent.id,
            "--json",
            "--",
            sys.executable,
            "-c",
            "import json; from pathlib import Path; Path('package.json').write_text(json.dumps({'dependencies':{'playwright':'1.58.0'}}))",
        ],
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    receipt = ReceiptV2.model_validate_json(result.stdout)
    assert receipt.passport_id == agent.id
    assert changes(receipt, "npm-manifest")[0].label == "playwright"
    assert str(project) not in result.stdout and str(registry.root) not in result.stdout
    assert "signup" not in result.stdout and "login" not in result.stdout


def test_large_previous_diffs_cannot_prevent_saving_current_receipt(project, store):
    from forkit_radar.sessions.details import Comparison
    from forkit_radar.sessions.models import FileChange
    from forkit_radar.sessions.storage import checked_bytes, fit_receipt

    first = stop(store, project)
    second = stop(store, project)
    files = tuple(
        FileChange(kind="modified", path=f"{'d' * 180}/{'f' * 180}{i}.py") for i in range(1600)
    )
    comparison = Comparison(
        baseline_session_id=first.session_id,
        comparison="complete",
        reason="same_project_and_selected_metadata_scope",
        skipped_sessions=0,
        file_changes=files,
        metadata=second.metadata,
    )
    raw = second.model_dump()
    raw.update(
        file_changes=files,
        meaningful_categories=("files",),
        since_previous=comparison,
        between_sessions=comparison,
    )
    receipt = ReceiptV2.model_validate(raw)
    assert len(canonical(receipt)) > 1_048_576
    fitted = fit_receipt(receipt)
    assert fitted.file_changes == files
    assert fitted.since_previous.reason == "comparison_record_limit"
    assert len(checked_bytes(fitted)) <= 1_048_576
    assert read_receipt(checked_bytes(fitted)) == fitted
    assert "size limit" in render(fitted)


def test_metadata_contract_rejects_fabricated_removals_and_duplicate_changes(project, store):
    from forkit_radar.sessions.details import Delta

    started, _ = store.start(project, tool="other")
    write(project / "package.json", {"dependencies": {"stripe": "1.0"}})
    receipt = store.finish(started.session_id)
    raw = receipt.metadata.model_dump()
    raw["changes"] = [raw["changes"][0], raw["changes"][0]]
    with pytest.raises(ValueError):
        Delta.model_validate(raw)
    raw = receipt.metadata.model_dump()
    coverage = next(c for c in raw["coverage"] if c["source"] == "npm-manifest")
    coverage.update(after="partial", comparison="partial")
    with pytest.raises(ValueError):
        Delta.model_validate(raw)


def test_unchanged_sessions_have_zero_categories_and_zero_previous_diffs(project, store):
    write(project / "package.json", {"dependencies": {"stripe": "1.0"}})
    stop(store, project)
    receipt = stop(store, project)
    assert receipt.meaningful_categories == () and receipt.metadata.changes == ()
    assert receipt.since_previous.comparison == "complete"
    assert (
        receipt.since_previous.metadata.changes == () and receipt.since_previous.file_changes == ()
    )
    assert "0 change categories" in render(receipt)


@pytest.mark.parametrize(
    "filename", ["Cargo.toml", "Gemfile", "composer.json", "Pipfile", "setup.py", "setup.cfg"]
)
def test_unsupported_manifests_without_locks_remain_visible(project, filename):
    (project / filename).write_text("do not execute")
    assert (
        source(capture(project, Selection(), b"k" * 32), "other-dependencies").state
        == "unsupported"
    )


def test_metadata_fact_budget_does_not_block_a_receipt(project, store):
    # Three individually supported files can exceed the combined budget.
    write(project / "package.json", {"dependencies": {f"pkg{i}": "1.0" for i in range(512)}})
    lock = {
        "lockfileVersion": 3,
        "packages": {f"node_modules/pkg{i}": {"version": "1.0.0"} for i in range(512)},
    }
    write(project / "package-lock.json", lock)
    write(project / "npm-shrinkwrap.json", lock)
    receipt = stop(store, project)
    assert receipt.dependency_comparison == "partial"
    assert receipt.passport_id is None
    assert all(c.after_reason == "metadata_entry_limit" for c in receipt.metadata.coverage)
    assert store.receipt() == receipt


def test_history_displays_metadata_changes_and_metadata_uncertainty(project, store):
    path = project / ".codex/config.toml"
    path.parent.mkdir()
    path.write_text('model="model-a"\n')
    started, _ = store.start(project, tool="other")
    path.write_text('model="model-b"\n')
    store.finish(started.session_id)
    command = [sys.executable, "-m", "forkit_radar.cli", "history", "--store", str(store.root)]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "0 file changes · 1 metadata changes" in result.stdout
    started, _ = store.start(project, tool="other")
    path.write_text("malformed]")
    store.finish(started.session_id)
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    assert "partial comparison" in result.stdout.splitlines()[0]
