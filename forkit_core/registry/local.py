"""
Local Registry — filesystem-backed passport store using JSON + SQLite.

Directory layout:
  <registry_root>/
    index.db              ← SQLite index (rebuildable)
    lineage.json          ← Serialized lineage graph
    models/
      <id>.json           ← One JSON file per ModelPassport
    agents/
      <id>.json           ← One JSON file per AgentPassport
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ..lineage import LineageGraph
from ..schemas import AgentPassport, ModelPassport
from .db import RegistryDB


class LocalRegistry:
    """
    Thread-unsafe single-process local registry.
    For concurrent use, wrap with a lock or use the SDK server mode (future).
    """

    def __init__(self, root: str | Path = "~/.forkit/registry"):
        self.root = Path(root).expanduser().resolve()
        self.models_dir = self.root / "models"
        self.agents_dir = self.root / "agents"
        self.db_path = self.root / "index.db"
        self.lineage_path = self.root / "lineage.json"
        self._lineage: LineageGraph | None = None

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #

    def init(self) -> None:
        """Create directory structure and initialize DB. Idempotent."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        with RegistryDB(self.db_path) as db:
            pass  # DDL runs on connect

    def _db(self) -> RegistryDB:
        return RegistryDB(self.db_path)

    # ------------------------------------------------------------------ #
    # Model operations
    # ------------------------------------------------------------------ #

    def register_model(self, passport: ModelPassport) -> str:
        """Persist a ModelPassport. Returns its ID."""
        self.init()
        data = passport.to_dict()
        path = self.models_dir / f"{passport.id}.json"
        path.write_text(json.dumps(data, indent=2, default=str))

        with self._db() as db:
            db.upsert(data, str(path.relative_to(self.root)))

        # Update lineage
        lineage = self.lineage
        lineage.register_model(data)
        lineage.save(self.lineage_path)

        return passport.id

    def get_model(self, passport_id: str) -> ModelPassport | None:
        path = self.models_dir / f"{passport_id}.json"
        if not path.exists():
            return None
        return ModelPassport(**json.loads(path.read_text()))

    # ------------------------------------------------------------------ #
    # Agent operations
    # ------------------------------------------------------------------ #

    def register_agent(self, passport: AgentPassport) -> str:
        """Persist an AgentPassport. Returns its ID."""
        self.init()
        data = passport.to_dict()
        path = self.agents_dir / f"{passport.id}.json"
        path.write_text(json.dumps(data, indent=2, default=str))

        with self._db() as db:
            db.upsert(data, str(path.relative_to(self.root)))

        lineage = self.lineage
        lineage.register_agent(data)
        lineage.save(self.lineage_path)

        return passport.id

    def get_agent(self, passport_id: str) -> AgentPassport | None:
        path = self.agents_dir / f"{passport_id}.json"
        if not path.exists():
            return None
        return AgentPassport(**json.loads(path.read_text()))

    # ------------------------------------------------------------------ #
    # Generic get
    # ------------------------------------------------------------------ #

    def get(self, passport_id: str) -> ModelPassport | AgentPassport | None:
        return self.get_model(passport_id) or self.get_agent(passport_id)

    def delete(self, passport_id: str) -> bool:
        deleted = False
        for directory in (self.models_dir, self.agents_dir):
            path = directory / f"{passport_id}.json"
            if path.exists():
                path.unlink()
                deleted = True
                break
        if deleted:
            with self._db() as db:
                db.delete(passport_id)
        return deleted

    # ------------------------------------------------------------------ #
    # Queries
    # ------------------------------------------------------------------ #

    def list(
        self,
        passport_type: str | None = None,
        status: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._db() as db:
            return db.list_all(passport_type=passport_type, status=status)

    def search(self, query: str) -> list[dict[str, Any]]:
        with self._db() as db:
            return db.search(query)

    def stats(self) -> dict[str, Any]:
        with self._db() as db:
            counts = db.count()
        lineage = self.lineage
        return {
            "models": counts.get("model", 0),
            "agents": counts.get("agent", 0),
            "total": sum(counts.values()),
            "lineage_nodes": len(lineage._nodes),
            "lineage_edges": len(lineage._edges),
            "registry_root": str(self.root),
        }

    # ------------------------------------------------------------------ #
    # Lineage access
    # ------------------------------------------------------------------ #

    @property
    def lineage(self) -> LineageGraph:
        if self._lineage is None:
            if self.lineage_path.exists():
                self._lineage = LineageGraph.load(self.lineage_path)
            else:
                self._lineage = LineageGraph()
        return self._lineage

    def reload_lineage(self) -> None:
        self._lineage = None

    # ------------------------------------------------------------------ #
    # Maintenance
    # ------------------------------------------------------------------ #

    def rebuild_index(self) -> int:
        """Rebuild the SQLite index from JSON files. Returns count of records indexed."""
        records: list[tuple[dict[str, Any], str]] = []

        for path in self.models_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                records.append((data, str(path.relative_to(self.root))))
            except Exception:
                pass

        for path in self.agents_dir.glob("*.json"):
            try:
                data = json.loads(path.read_text())
                records.append((data, str(path.relative_to(self.root))))
            except Exception:
                pass

        with self._db() as db:
            db.rebuild_from_records(records)

        return len(records)

    def verify_passport(self, passport_id: str) -> dict[str, Any]:
        """Verify the integrity of a stored passport by re-computing its ID."""
        passport = self.get(passport_id)
        if passport is None:
            return {"valid": False, "reason": "not_found"}

        recomputed = passport._compute_id()
        match = recomputed == passport_id

        return {
            "valid": match,
            "stored_id": passport_id,
            "recomputed_id": recomputed,
            "reason": "ok" if match else "id_mismatch",
        }
