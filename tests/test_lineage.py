"""Tests for the LineageGraph."""

import pytest

from forkit_core.lineage import EdgeType, LineageEdge, LineageGraph, LineageNode, NodeType


def _model_node(id: str, name: str = "model", version: str = "1.0.0") -> LineageNode:
    return LineageNode(id=id, node_type=NodeType.MODEL, name=name, version=version)


def _agent_node(id: str, name: str = "agent", version: str = "1.0.0") -> LineageNode:
    return LineageNode(id=id, node_type=NodeType.AGENT, name=name, version=version)


class TestLineageGraph:
    def test_add_node(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        assert g.get_node("m1") is not None

    def test_add_node_idempotent(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        g.add_node(_model_node("m1"))
        assert len(g._nodes) == 1

    def test_add_edge(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        g.add_node(_model_node("m2"))
        g.add_edge(LineageEdge("m2", "m1", EdgeType.DERIVED_FROM))
        assert len(g._edges) == 1

    def test_edge_missing_node_raises(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        with pytest.raises(KeyError):
            g.add_edge(LineageEdge("m1", "nonexistent", EdgeType.DERIVED_FROM))

    def test_cycle_detection(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        g.add_node(_model_node("m2"))
        g.add_edge(LineageEdge("m1", "m2", EdgeType.DERIVED_FROM))
        with pytest.raises(ValueError):
            g.add_edge(LineageEdge("m2", "m1", EdgeType.DERIVED_FROM))

    def test_ancestors(self):
        g = LineageGraph()
        g.add_node(_model_node("base"))
        g.add_node(_model_node("ft1"))
        g.add_node(_model_node("ft2"))
        g.add_edge(LineageEdge("ft1", "base", EdgeType.DERIVED_FROM))
        g.add_edge(LineageEdge("ft2", "ft1", EdgeType.DERIVED_FROM))

        ancestors = g.ancestors("ft2")
        ids = {n.id for n in ancestors}
        assert "ft1" in ids
        assert "base" in ids
        assert "ft2" not in ids

    def test_descendants(self):
        g = LineageGraph()
        g.add_node(_model_node("base"))
        g.add_node(_model_node("ft1"))
        g.add_node(_agent_node("a1"))
        g.add_edge(LineageEdge("ft1", "base", EdgeType.DERIVED_FROM))
        g.add_edge(LineageEdge("a1", "ft1", EdgeType.BUILT_ON))

        desc = g.descendants("base")
        ids = {n.id for n in desc}
        assert "ft1" in ids
        assert "a1" in ids

    def test_nodes_by_type(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        g.add_node(_model_node("m2"))
        g.add_node(_agent_node("a1"))
        assert len(g.nodes_by_type(NodeType.MODEL)) == 2
        assert len(g.nodes_by_type(NodeType.AGENT)) == 1

    def test_json_roundtrip(self):
        import json
        g = LineageGraph()
        g.add_node(_model_node("m1", "base-model"))
        g.add_node(_agent_node("a1", "my-agent"))
        g.add_edge(LineageEdge("a1", "m1", EdgeType.BUILT_ON))

        data = json.loads(g.to_json())
        assert len(data["nodes"]) == 2
        assert len(data["edges"]) == 1

    def test_save_and_load(self, tmp_path):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        g.add_node(_agent_node("a1"))
        g.add_edge(LineageEdge("a1", "m1", EdgeType.BUILT_ON))

        path = tmp_path / "lineage.json"
        g.save(path)

        g2 = LineageGraph.load(path)
        assert g2.get_node("m1") is not None
        assert g2.get_node("a1") is not None

    def test_summary(self):
        g = LineageGraph()
        g.add_node(_model_node("m1"))
        g.add_node(_agent_node("a1"))
        s = g.summary()
        assert "2 nodes" in s
        assert "1 models" in s
        assert "1 agents" in s


@pytest.mark.parametrize("direction", ["ancestors", "descendants"])
def test_deep_lineage_chain(direction):
    graph = LineageGraph()
    size = 3000
    for i in range(size):
        graph.add_node(_model_node(str(i)))
    # Add from the leaf backwards so cycle checks do not revisit the whole chain.
    for i in range(size - 1, 0, -1):
        graph.add_edge(LineageEdge(str(i), str(i - 1), EdgeType.DERIVED_FROM))

    start = str(size - 1) if direction == "ancestors" else "0"
    expected = range(size - 2, -1, -1) if direction == "ancestors" else range(1, size)
    assert [node.id for node in getattr(graph, direction)(start)] == [str(i) for i in expected]


def test_lineage_preserves_depth_first_order_and_visits_shared_nodes_once():
    graph = LineageGraph()
    for node_id in "abcde":
        graph.add_node(_model_node(node_id))
    for source, target in [("a", "b"), ("a", "c"), ("b", "c"), ("b", "d"), ("c", "e")]:
        graph.add_edge(LineageEdge(source, target, EdgeType.DERIVED_FROM))

    assert [node.id for node in graph.ancestors("a")] == ["b", "c", "e", "d"]
    assert [node.id for node in graph.descendants("e")] == ["c", "a", "b"]
