"""
forkit.domain.lineage
─────────────────────
Directed acyclic graph (DAG) tracking provenance relationships between
model and agent passports.

Node types
──────────
  model:<id>   — a ModelPassport
  agent:<id>   — an AgentPassport

Edge types
──────────
  DERIVED_FROM   model  → model  (fine-tune, distillation, merge)
  BUILT_ON       agent  → model  (agent uses this model)
  FORKED_FROM    agent  → agent  (agent derived from another agent)

Design
──────
  - Pure Python, zero external dependencies.
  - In-memory adjacency dicts + edge list.
  - DFS cycle detection on every add_edge call.
  - JSON serialisation / deserialisation for persistence via the registry.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any

__all__ = [
    "NodeType",
    "EdgeType",
    "LineageNode",
    "LineageEdge",
    "LineageGraph",
]


class NodeType(str, Enum):
    MODEL = "model"
    AGENT = "agent"


class EdgeType(str, Enum):
    DERIVED_FROM = "derived_from"   # model → parent model
    BUILT_ON     = "built_on"       # agent → model
    FORKED_FROM  = "forked_from"    # agent → parent agent


class LineageNode:
    """Lightweight provenance node — holds just what is needed for graph traversal."""

    __slots__ = ("id", "node_type", "name", "version", "metadata")

    def __init__(
        self,
        id: str,
        node_type: NodeType,
        name: str,
        version: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self.id        = id
        self.node_type = node_type
        self.name      = name
        self.version   = version
        self.metadata  = metadata or {}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id":        self.id,
            "node_type": self.node_type.value if isinstance(self.node_type, Enum) else self.node_type,
            "name":      self.name,
            "version":   self.version,
            "metadata":  self.metadata,
        }

    def __repr__(self) -> str:
        return f"<LineageNode {self.node_type} {self.name!r} v{self.version}>"


class LineageEdge:
    """Directed provenance edge between two nodes."""

    __slots__ = ("source_id", "target_id", "edge_type", "reason", "created_at")

    def __init__(
        self,
        source_id: str,
        target_id: str,
        edge_type: EdgeType,
        reason: str | None = None,
    ) -> None:
        self.source_id  = source_id
        self.target_id  = target_id
        self.edge_type  = edge_type
        self.reason     = reason
        self.created_at = datetime.now(timezone.utc).isoformat()

    def to_dict(self) -> dict[str, Any]:
        return {
            "source":     self.source_id,
            "target":     self.target_id,
            "edge_type":  self.edge_type.value if isinstance(self.edge_type, Enum) else self.edge_type,
            "reason":     self.reason,
            "created_at": self.created_at,
        }

    def __repr__(self) -> str:
        et = self.edge_type.value if isinstance(self.edge_type, Enum) else self.edge_type
        return f"<LineageEdge {self.source_id[:8]} --{et}--> {self.target_id[:8]}>"


class LineageGraph:
    """
    In-memory DAG of passport lineage.

    Thread-unsafe. For multi-process use, persist to JSON and reload per process.
    """

    def __init__(self) -> None:
        self._nodes: dict[str, LineageNode] = {}
        self._edges: list[LineageEdge]      = []
        self._adj:   dict[str, list[str]]   = {}   # source → [targets]
        self._radj:  dict[str, list[str]]   = {}   # target → [sources]

    # ── Mutation ───────────────────────────────────────────────────────────────

    def add_node(self, node: LineageNode) -> None:
        """Add a node. Idempotent — adding the same id twice is a no-op."""
        if node.id in self._nodes:
            return
        self._nodes[node.id] = node
        self._adj.setdefault(node.id, [])
        self._radj.setdefault(node.id, [])

    def add_edge(self, edge: LineageEdge) -> None:
        """
        Add a directed edge.

        Raises KeyError if either endpoint is not registered.
        Raises ValueError if the edge would create a cycle.
        """
        if edge.source_id not in self._nodes:
            raise KeyError(f"Source node not in graph: {edge.source_id}")
        if edge.target_id not in self._nodes:
            raise KeyError(f"Target node not in graph: {edge.target_id}")
        if self._would_cycle(edge.source_id, edge.target_id):
            raise ValueError(
                f"Edge {edge.source_id[:8]}→{edge.target_id[:8]} would create a cycle"
            )
        self._edges.append(edge)
        self._adj[edge.source_id].append(edge.target_id)
        self._radj[edge.target_id].append(edge.source_id)

    # ── Convenience constructors from passport dicts ───────────────────────────

    def register_model(self, passport_dict: dict[str, Any]) -> LineageNode:
        """Add a model node and optionally wire it to its parent model."""
        node = LineageNode(
            id        = passport_dict["id"],
            node_type = NodeType.MODEL,
            name      = passport_dict["name"],
            version   = passport_dict["version"],
            metadata  = {"creator": passport_dict.get("creator", {})},
        )
        self.add_node(node)

        parent_id = passport_dict.get("base_model_id")
        if parent_id and parent_id in self._nodes:
            self.add_edge(LineageEdge(
                source_id = passport_dict["id"],
                target_id = parent_id,
                edge_type = EdgeType.DERIVED_FROM,
                reason    = passport_dict.get("fine_tuning_method"),
            ))
        return node

    def register_agent(self, passport_dict: dict[str, Any]) -> LineageNode:
        """Add an agent node and wire it to its model and optional parent agent."""
        node = LineageNode(
            id        = passport_dict["id"],
            node_type = NodeType.AGENT,
            name      = passport_dict["name"],
            version   = passport_dict["version"],
            metadata  = {
                "role":    passport_dict.get("role"),
                "creator": passport_dict.get("creator", {}),
            },
        )
        self.add_node(node)

        model_id = passport_dict.get("model_id")
        if model_id and model_id in self._nodes:
            self.add_edge(LineageEdge(
                source_id = passport_dict["id"],
                target_id = model_id,
                edge_type = EdgeType.BUILT_ON,
            ))

        parent_agent_id = passport_dict.get("parent_agent_id")
        if parent_agent_id and parent_agent_id in self._nodes:
            self.add_edge(LineageEdge(
                source_id = passport_dict["id"],
                target_id = parent_agent_id,
                edge_type = EdgeType.FORKED_FROM,
                reason    = passport_dict.get("fork_reason"),
            ))
        return node

    # ── Queries ────────────────────────────────────────────────────────────────

    def get_node(self, node_id: str) -> LineageNode | None:
        return self._nodes.get(node_id)

    def ancestors(self, node_id: str) -> list[LineageNode]:
        """All nodes reachable upstream (following outward edges)."""
        visited: set[str] = set()
        result:  list[LineageNode] = []
        self._dfs(node_id, self._adj, visited, result)
        return [n for n in result if n.id != node_id]

    def descendants(self, node_id: str) -> list[LineageNode]:
        """All nodes that point to this node (reverse traversal)."""
        visited: set[str] = set()
        result:  list[LineageNode] = []
        self._dfs(node_id, self._radj, visited, result)
        return [n for n in result if n.id != node_id]

    def edges_for(self, node_id: str) -> list[LineageEdge]:
        """All edges where node_id is source or target."""
        return [e for e in self._edges
                if e.source_id == node_id or e.target_id == node_id]

    def nodes_by_type(self, node_type: NodeType) -> list[LineageNode]:
        return [n for n in self._nodes.values() if n.node_type == node_type]

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "nodes": [n.to_dict() for n in self._nodes.values()],
            "edges": [e.to_dict() for e in self._edges],
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, path: str | Path) -> None:
        Path(path).write_text(self.to_json())

    @classmethod
    def load(cls, path: str | Path) -> LineageGraph:
        data = json.loads(Path(path).read_text())
        g = cls()
        for nd in data.get("nodes", []):
            g.add_node(LineageNode(
                id        = nd["id"],
                node_type = NodeType(nd["node_type"]),
                name      = nd["name"],
                version   = nd["version"],
                metadata  = nd.get("metadata", {}),
            ))
        for ed in data.get("edges", []):
            edge = LineageEdge(
                source_id = ed["source"],
                target_id = ed["target"],
                edge_type = EdgeType(ed["edge_type"]),
                reason    = ed.get("reason"),
            )
            edge.created_at = ed.get("created_at", edge.created_at)
            g._edges.append(edge)
            g._adj[ed["source"]].append(ed["target"])
            g._radj[ed["target"]].append(ed["source"])
        return g

    def summary(self) -> str:
        n_m = len(self.nodes_by_type(NodeType.MODEL))
        n_a = len(self.nodes_by_type(NodeType.AGENT))
        return (
            f"LineageGraph — {len(self._nodes)} nodes "
            f"({n_m} models, {n_a} agents), "
            f"{len(self._edges)} edges"
        )

    # ── Internal ───────────────────────────────────────────────────────────────

    def _dfs(
        self,
        start: str,
        adj: dict[str, list[str]],
        visited: set[str],
        result: list[LineageNode],
    ) -> None:
        stack = [start]
        while stack:
            node = stack.pop()
            if node in visited:
                continue
            visited.add(node)
            if node in self._nodes:
                result.append(self._nodes[node])
            # Push in reverse so the first neighbor is visited first, as in recursive DFS.
            stack.extend(reversed(adj.get(node, [])))

    def _would_cycle(self, source: str, target: str) -> bool:
        """DFS from target; True if we can reach source."""
        visited: set[str] = set()
        stack = [target]
        while stack:
            node = stack.pop()
            if node == source:
                return True
            if node not in visited:
                visited.add(node)
                stack.extend(self._adj.get(node, []))
        return False
