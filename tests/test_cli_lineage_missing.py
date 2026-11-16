"""Missing passports and empty relation sections in the lineage CLI."""

import pytest
from typer.testing import CliRunner

from forkit.cli.main import app
from forkit.registry.local import LocalRegistry
from forkit.schemas import ModelPassport


@pytest.fixture()
def registry(tmp_path, monkeypatch):
    monkeypatch.setattr("forkit.cli.main._REGISTRY_ROOT", tmp_path)
    return LocalRegistry(root=tmp_path)


@pytest.mark.parametrize("passport_id", ["deadbeef", "f" * 64])
def test_lineage_unknown_id_fails(registry, passport_id):
    result = CliRunner().invoke(app, ["lineage", passport_id])

    assert result.exit_code == 1
    assert result.stderr == f"Not found: {passport_id}\n"
    assert result.stdout == ""


def test_lineage_registered_model_without_relations(registry, base_model):
    passport_id = registry.register_model(base_model)

    result = CliRunner().invoke(app, ["lineage", passport_id])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    assert result.stdout == (
        f"\nAncestors of {passport_id[:16]}...:\n  (none)\n"
        "\nDescendants:\n  (none)\n"
    )


@pytest.mark.parametrize("direction", ["ancestors", "descendants"])
def test_lineage_keeps_related_nodes_and_marks_only_empty_section(registry, base_model, direction):
    parent_id = registry.register_model(base_model)
    child_data = {**base_model.to_dict(), "name": "child", "base_model_id": parent_id}
    child_data.pop("id")
    child = ModelPassport.from_dict(child_data)
    child_id = registry.register_model(child)
    query_id = child_id if direction == "ancestors" else parent_id
    related = base_model if direction == "ancestors" else child

    result = CliRunner().invoke(app, ["lineage", query_id])

    assert result.exit_code == 0, result.output
    assert result.stderr == ""
    ancestors, descendants = result.stdout.split("\nDescendants:\n")
    populated, empty = (ancestors, descendants) if direction == "ancestors" else (descendants, ancestors)
    assert f"{related.name} v{related.version}  {related.id[:16]}..." in populated
    assert "(none)" not in populated
    assert "  (none)\n" in empty
    assert result.stdout.count("(none)") == 1
