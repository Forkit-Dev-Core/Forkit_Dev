"""Regression tests for human-readable lineage labels."""

import pytest
from typer.testing import CliRunner

from forkit.cli.main import app
from forkit.domain.lineage import EdgeType, LineageEdge, LineageGraph, LineageNode, NodeType


@pytest.mark.parametrize("node_type", list(NodeType))
def test_lineage_node_repr_uses_type_value(node_type):
    node = LineageNode("node-id", node_type, "test-node", "1.0.0")

    assert repr(node) == f"<LineageNode {node_type.value} 'test-node' v1.0.0>"
    assert "NodeType" not in repr(node)


@pytest.mark.parametrize("node_type", list(NodeType))
@pytest.mark.parametrize("direction", ["ancestors", "descendants"])
def test_lineage_cli_uses_type_values(tmp_path, monkeypatch, node_type, direction):
    graph = LineageGraph()
    graph.add_node(LineageNode("root-id", node_type, "root", "1.0.0"))
    graph.add_node(LineageNode("child-id", node_type, "child", "2.0.0"))
    edge_type = EdgeType.DERIVED_FROM if node_type == NodeType.MODEL else EdgeType.FORKED_FROM
    graph.add_edge(LineageEdge("child-id", "root-id", edge_type))
    graph.save(tmp_path / "lineage.json")
    monkeypatch.setattr("forkit.cli.main._REGISTRY_ROOT", tmp_path)
    query_id, expected = (
        ("child-id", "root v1.0.0  root-id...")
        if direction == "ancestors"
        else ("root-id", "child v2.0.0  child-id...")
    )

    result = CliRunner().invoke(app, ["lineage", query_id])

    assert result.exit_code == 0, result.output
    assert f"[{node_type.value}] {expected}" in result.output
    assert "NodeType" not in result.output


def test_lineage_cli_isolated_node_has_no_labels(tmp_path, monkeypatch):
    graph = LineageGraph()
    graph.add_node(LineageNode("isolated-id", NodeType.MODEL, "isolated", "1.0.0"))
    graph.save(tmp_path / "lineage.json")
    monkeypatch.setattr("forkit.cli.main._REGISTRY_ROOT", tmp_path)

    result = CliRunner().invoke(app, ["lineage", "isolated-id"])

    assert result.exit_code == 0, result.output
    assert result.output in {
        "\nAncestors of isolated-id...:\n\nDescendants:\n",
        "\nAncestors of isolated-id...:\n  (none)\n\nDescendants:\n  (none)\n",
    }
