"""Upgrade from persisted passports accepted before strict version validation."""

import json
from copy import deepcopy
from importlib import import_module
from pathlib import Path

import pytest

from forkit.domain.integrity import verify_passport_id
from forkit.registry.local import LocalRegistry

FIXTURE = Path(__file__).parent / "fixtures" / "legacy-version-registry.json"


@pytest.fixture(params=["dataclass", "pydantic"])
def backend(request, monkeypatch):
    prefix = ""
    if request.param == "pydantic":
        pytest.importorskip("pydantic", minversion="2.0")
        prefix = "pydantic."
    classes = {}
    for kind in ("model", "agent"):
        cls = getattr(import_module(f"forkit.schemas.{prefix}{kind}"), f"{kind.title()}Passport")
        monkeypatch.setattr(f"forkit.registry.local.{kind.title()}Passport", cls)
        classes[kind] = cls
    return classes


@pytest.fixture
def upgraded_registry(tmp_path, backend):
    snapshot = json.loads(FIXTURE.read_text(encoding="utf-8"))
    root = tmp_path / "old-registry"
    # Start from persisted files, not register_* under the new validator.
    for kind in ("models", "agents"):
        (root / kind).mkdir(parents=True)
        for data in snapshot[kind]:
            (root / kind / f"{data['id']}.json").write_text(json.dumps(data), encoding="utf-8")
    (root / "lineage.json").write_text(json.dumps(snapshot["lineage"]), encoding="utf-8")
    return LocalRegistry(root), snapshot


def stored_files(root):
    return {path.relative_to(root): path.read_bytes() for path in root.rglob("*") if path.is_file()}


@pytest.mark.parametrize("kind", ["model", "agent"])
def test_upgrade_keeps_invalid_records_inspectable_and_valid_records_loadable(upgraded_registry, kind):
    registry, snapshot = upgraded_registry
    legacy, normal = snapshot[f"{kind}s"]
    before = stored_files(registry.root)
    assert registry.rebuild_index() == 4
    assert any(row["id"] == legacy["id"] for row in registry.list())
    # Rebuilding the index does not validate, repair or discard source JSON/lineage.
    assert {path: stored_files(registry.root)[path] for path in before} == before
    after_rebuild = stored_files(registry.root)
    loader = getattr(registry, f"get_{kind}")
    with pytest.raises(ValueError, match="Version must be"):
        loader(legacy["id"])
    assert verify_passport_id(legacy)["valid"]  # Old ID is consistent, version is invalid.
    assert registry.get_raw(legacy["id"]) == legacy
    fetched = loader(normal["id"])
    assert fetched.id == normal["id"]
    assert fetched.version == normal["version"]
    assert verify_passport_id(fetched.to_dict())["valid"]
    raw = registry.get_raw(legacy["id"])
    raw["creator"]["name"] = "Local edit only"
    assert registry.get_raw(legacy["id"]) == legacy
    assert stored_files(registry.root) == after_rebuild


@pytest.mark.parametrize("kind", ["model", "agent"])
def test_explicit_recovery_preserves_original_records_and_lineage(upgraded_registry, backend, kind):
    original, snapshot = upgraded_registry
    legacy = snapshot[f"{kind}s"][0]
    before = stored_files(original.root)
    data = deepcopy(original.get_raw(legacy["id"]))
    data.pop("id")  # Essential: replaying an old ID would not derive a corrected identity.
    data["version"] = "1.0.0"
    data.setdefault("metadata", {})["recovery"] = {
        "original_passport_id": legacy["id"],
        "reason": "Correct malformed legacy version",
    }
    corrected = backend[kind].from_dict(data)
    assert corrected.id != legacy["id"]
    assert verify_passport_id(corrected.to_dict())["valid"]
    recovery = LocalRegistry(original.root.parent / "recovered-registry")
    getattr(recovery, f"register_{kind}")(corrected)
    assert getattr(recovery, f"get_{kind}")(corrected.id).id == corrected.id
    assert recovery.verify_passport(corrected.id)["valid"]
    assert original.get_raw(legacy["id"]) == legacy
    assert stored_files(original.root) == before
    assert original.lineage.to_dict() == snapshot["lineage"]
    assert original.lineage.get_node(corrected.id) is None
    assert recovery.lineage.get_node(corrected.id) is not None
    assert recovery.lineage.edges_for(corrected.id) == []  # No invented derivation/fork.
    assert snapshot["models"][1]["base_model_id"] == snapshot["models"][0]["id"]
    assert snapshot["agents"][1]["model_id"] == snapshot["models"][0]["id"]
    assert snapshot["agents"][1]["parent_agent_id"] == snapshot["agents"][0]["id"]
    with pytest.raises(ValueError, match="Version must be"):
        getattr(original, f"get_{kind}")(legacy["id"])
    # Recovery must still reject a proposed replacement with another invalid version.
    data["version"] = "a.b"
    with pytest.raises(ValueError, match="Version must be"):
        backend[kind].from_dict(data)


def test_raw_read_needs_no_index_or_initialization(upgraded_registry, tmp_path):
    registry, snapshot = upgraded_registry
    before = stored_files(registry.root)
    for kind in ("models", "agents"):
        for data in snapshot[kind]:
            assert registry.get_raw(data["id"]) == data
    assert registry.get_raw("0" * 64) is None
    assert stored_files(registry.root) == before
    missing = LocalRegistry(tmp_path / "missing")
    assert missing.get_raw("0" * 64) is None
    assert not missing.root.exists()


def test_documented_model_recovery_example(upgraded_registry, monkeypatch):
    original, snapshot = upgraded_registry
    before = stored_files(original.root)
    monkeypatch.chdir(original.root.parent)
    spec = (FIXTURE.parents[2] / "docs" / "identity-spec.md").read_text(encoding="utf-8")
    code = "from copy import deepcopy" + spec.split("from copy import deepcopy", 1)[1].split("```", 1)[0]
    code = code.replace("<full-original-model-id>", snapshot["models"][0]["id"])
    exec(compile(code, "documented-recovery-example", "exec"), {})
    assert stored_files(original.root) == before
    staged = stored_files(original.root.parent / "recovered-registry")
    # A repeated example must refuse an existing destination, not overwrite it.
    with pytest.raises(ValueError, match="Choose a new recovery directory"):
        exec(compile(code, "documented-recovery-example", "exec"), {})
    assert stored_files(original.root.parent / "recovered-registry") == staged


@pytest.mark.parametrize("passport_id", ["", "a" * 63, "A" * 64, "g" * 64, "../lineage", "a/" * 32])
def test_raw_read_rejects_partial_or_unsafe_ids(tmp_path, passport_id):
    registry = LocalRegistry(tmp_path / "missing")
    with pytest.raises(ValueError, match="full lowercase SHA-256"):
        registry.get_raw(passport_id)
    assert not registry.root.exists()


@pytest.mark.parametrize("content", ["[]", "null", '"text"', "{bad json"])
def test_raw_read_does_not_hide_malformed_json(tmp_path, content):
    registry = LocalRegistry(tmp_path)
    registry.models_dir.mkdir()
    path = registry.models_dir / f"{'a' * 64}.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        registry.get_raw("a" * 64)
    assert path.read_text(encoding="utf-8") == content


@pytest.mark.parametrize("kind", ["models", "agents"])
def test_inspect_cli_explains_validation_failure_and_offers_explicit_raw_read(
    upgraded_registry, monkeypatch, kind
):
    pytest.importorskip("typer")
    from typer.testing import CliRunner

    cli = import_module("forkit.cli.main")
    registry, snapshot = upgraded_registry
    monkeypatch.setattr(cli, "_REGISTRY_ROOT", registry.root)
    legacy, normal = snapshot[kind]
    before = stored_files(registry.root)
    runner = CliRunner()
    failed = runner.invoke(cli.app, ["inspect", legacy["id"]])
    assert failed.exit_code == 1
    assert "Version must be" in failed.output
    assert "--raw" in failed.output
    raw = runner.invoke(cli.app, ["inspect", legacy["id"], "--raw"])
    assert raw.exit_code == 0, raw.output
    assert json.loads(raw.stdout) == legacy
    valid = runner.invoke(cli.app, ["inspect", normal["id"]])
    assert valid.exit_code == 0, valid.output
    assert json.loads(valid.stdout)["id"] == normal["id"]
    assert stored_files(registry.root) == before


def test_raw_inspect_cli_reports_missing_or_malformed_record(tmp_path, monkeypatch):
    pytest.importorskip("typer")
    from typer.testing import CliRunner

    cli = import_module("forkit.cli.main")
    registry = LocalRegistry(tmp_path)
    monkeypatch.setattr(cli, "_REGISTRY_ROOT", tmp_path)
    runner = CliRunner()
    missing = runner.invoke(cli.app, ["inspect", "0" * 64, "--raw"])
    assert missing.exit_code == 1
    assert "Not found" in missing.output
    registry.models_dir.mkdir()
    path = registry.models_dir / f"{'a' * 64}.json"
    path.write_text("[]", encoding="utf-8")
    malformed = runner.invoke(cli.app, ["inspect", "a" * 64, "--raw"])
    assert malformed.exit_code == 1
    assert "Stored passport JSON must be an object" in malformed.output
    unsafe = runner.invoke(cli.app, ["inspect", "../lineage", "--raw"])
    assert unsafe.exit_code == 1
    assert "full lowercase SHA-256" in unsafe.output
