"""
forkit.registry.local
─────────────────────
Filesystem-backed local passport registry: JSON files + SQLite index.

Directory layout
────────────────
  <registry_root>/
    index.db          ← SQLite index (rebuildable from JSON)
    lineage.json      ← Serialised LineageGraph
    models/
      <id>.json       ← One file per ModelPassport
    agents/
      <id>.json       ← One file per AgentPassport

Design decisions
────────────────
- JSON is the source of truth; SQLite is a rebuildable index.
- The lineage graph is persisted as JSON alongside the JSON store.
- Thread-unsafe by design; wrap with a lock for concurrent use.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

from ..domain.hashing import HashEngine
from ..domain.lineage import LineageGraph
from ..domain.integrity import verify_passport_id
from ..schemas import ModelPassport, AgentPassport
from .db import RegistryDB


class LocalRegistry:
    """
    Single-process local passport registry.

    Default root: ~/.forkit/registry
    Call init() to create directories and initialise the DB.
    """

    def __init__(self, root: str | Path = "~/.forkit/registry") -> None:
        self.root         = Path(root).expanduser().resolve()
        self.models_dir   = self.root / "models"
        self.agents_dir   = self.root / "agents"
        self.db_path      = self.root / "index.db"
        self.lineage_path = self.root / "lineage.json"
        self.outbox_path  = self.root / "outbox.jsonl"
        self.sync_state_path = self.root / "sync_state.json"
        self.sync_inbox_dir = self.root / "sync_inbox"
        self.sync_batches_path = self.root / "sync_inbox.jsonl"
        self._lineage: LineageGraph | None = None
        self._outbox_cursor: int | None = None

    # ── Lifecycle ──────────────────────────────────────────────────────────────

    def init(self) -> None:
        """Create directory tree and initialise the DB. Idempotent."""
        self.models_dir.mkdir(parents=True, exist_ok=True)
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        self.sync_inbox_dir.mkdir(parents=True, exist_ok=True)
        self.outbox_path.touch(exist_ok=True)
        self.sync_batches_path.touch(exist_ok=True)
        if not self.sync_state_path.exists():
            self.sync_state_path.write_text("{}\n", encoding="utf-8")
        with RegistryDB(self.db_path):
            pass  # DDL runs on connect

    def _db(self) -> RegistryDB:
        return RegistryDB(self.db_path)

    # ── Model CRUD ─────────────────────────────────────────────────────────────

    def register_model(self, passport: ModelPassport, *, record_change: bool = True) -> str:
        """Persist a ModelPassport. Returns its ID."""
        self.init()
        data = passport.to_dict()
        path = self.models_dir / f"{passport.id}.json"
        relative_path = str(path.relative_to(self.root))
        path.write_text(json.dumps(data, indent=2, default=str))
        with self._db() as db:
            db.upsert(data, relative_path)
        self.lineage.register_model(data)
        self.lineage.save(self.lineage_path)
        if record_change:
            self._append_change(
                operation="upsert",
                passport_id=passport.id,
                passport_type=data.get("passport_type", "model"),
                json_path=relative_path,
                document=data,
            )
        return passport.id

    def get_model(self, passport_id: str) -> ModelPassport | None:
        path = self.models_dir / f"{passport_id}.json"
        if not path.exists():
            return None
        return ModelPassport.from_dict(json.loads(path.read_text()))

    # ── Agent CRUD ─────────────────────────────────────────────────────────────

    def register_agent(self, passport: AgentPassport, *, record_change: bool = True) -> str:
        """Persist an AgentPassport. Returns its ID."""
        self.init()
        data = passport.to_dict()
        path = self.agents_dir / f"{passport.id}.json"
        relative_path = str(path.relative_to(self.root))
        path.write_text(json.dumps(data, indent=2, default=str))
        with self._db() as db:
            db.upsert(data, relative_path)
        self.lineage.register_agent(data)
        self.lineage.save(self.lineage_path)
        if record_change:
            self._append_change(
                operation="upsert",
                passport_id=passport.id,
                passport_type=data.get("passport_type", "agent"),
                json_path=relative_path,
                document=data,
            )
        return passport.id

    def get_agent(self, passport_id: str) -> AgentPassport | None:
        path = self.agents_dir / f"{passport_id}.json"
        if not path.exists():
            return None
        return AgentPassport.from_dict(json.loads(path.read_text()))

    # ── Generic ────────────────────────────────────────────────────────────────

    def get(self, passport_id: str) -> ModelPassport | AgentPassport | None:
        return self.get_model(passport_id) or self.get_agent(passport_id)

    def delete(self, passport_id: str, *, record_change: bool = True) -> bool:
        deleted = False
        deleted_type: str | None = None
        for deleted_type, directory in (("model", self.models_dir), ("agent", self.agents_dir)):
            path = directory / f"{passport_id}.json"
            if path.exists():
                path.unlink()
                deleted = True
                break
        if deleted:
            with self._db() as db:
                db.delete(passport_id)
            if deleted_type is not None and record_change:
                self._append_change(
                    operation="delete",
                    passport_id=passport_id,
                    passport_type=deleted_type,
                )
        return deleted

    def apply_changes(
        self,
        items: list[dict[str, Any]],
        *,
        record_change: bool = False,
    ) -> dict[str, int]:
        """Apply exported change records into the local registry."""
        self.init()
        applied = 0
        upserts = 0
        deletes = 0

        for index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"'items[{index}]' must be an object.")

            operation = item.get("operation")
            passport_id = item.get("passport_id")
            if not isinstance(passport_id, str) or not passport_id:
                raise ValueError(f"'items[{index}].passport_id' must be a non-empty string.")

            if operation == "upsert":
                document = item.get("document")
                if not isinstance(document, dict):
                    raise ValueError(f"'items[{index}].document' must be an object for upserts.")
                if document.get("id") != passport_id:
                    raise ValueError(
                        f"'items[{index}].document.id' must match 'items[{index}].passport_id'."
                    )

                passport_type = document.get("passport_type") or item.get("passport_type")
                if passport_type == "model":
                    passport = ModelPassport.from_dict(document)
                    verification = verify_passport_id(passport.to_dict())
                    if not verification.get("valid"):
                        raise ValueError(
                            f"'items[{index}]' contains a model passport with an invalid identity."
                        )
                    self.register_model(passport, record_change=record_change)
                elif passport_type == "agent":
                    passport = AgentPassport.from_dict(document)
                    verification = verify_passport_id(passport.to_dict())
                    if not verification.get("valid"):
                        raise ValueError(
                            f"'items[{index}]' contains an agent passport with an invalid identity."
                        )
                    self.register_agent(passport, record_change=record_change)
                else:
                    raise ValueError(
                        f"'items[{index}].passport_type' must be 'model' or 'agent' for upserts."
                    )
                applied += 1
                upserts += 1
                continue

            if operation == "delete":
                if self.delete(passport_id, record_change=record_change):
                    applied += 1
                    deletes += 1
                continue

            raise ValueError(f"'items[{index}].operation' must be 'upsert' or 'delete'.")

        return {
            "applied": applied,
            "upserts": upserts,
            "deletes": deletes,
        }

    # ── Queries ────────────────────────────────────────────────────────────────

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

    def export_changes(
        self,
        *,
        after: int = 0,
        limit: int = 100,
        passport_type: str | None = None,
    ) -> dict[str, Any]:
        """Return cursor-ordered change records with current passport documents."""
        if after < 0:
            raise ValueError("'after' must be greater than or equal to 0.")
        if limit < 1:
            raise ValueError("'limit' must be greater than or equal to 1.")

        filtered: list[dict[str, Any]] = []
        for record in self._read_outbox():
            cursor = record.get("cursor")
            if not isinstance(cursor, int) or cursor <= after:
                continue
            if passport_type is not None and record.get("passport_type") != passport_type:
                continue
            filtered.append(record)

        items: list[dict[str, Any]] = []
        for record in filtered[:limit]:
            item = dict(record)
            if item.get("operation") == "delete":
                item["document"] = None
            else:
                snapshot = item.get("document")
                if isinstance(snapshot, dict):
                    item["document"] = snapshot
                else:
                    passport = self.get(item["passport_id"])
                    item["document"] = passport.to_dict() if passport is not None else None
            items.append(item)

        cursor = items[-1]["cursor"] if items else after
        return {
            "cursor": cursor,
            "has_more": len(filtered) > limit,
            "items": items,
        }

    def stats(self) -> dict[str, Any]:
        with self._db() as db:
            counts = db.count()
        lg = self.lineage
        return {
            "models":         counts.get("model", 0),
            "agents":         counts.get("agent", 0),
            "total":          sum(counts.values()),
            "lineage_nodes":  len(lg._nodes),
            "lineage_edges":  len(lg._edges),
            "registry_root":  str(self.root),
        }

    def get_sync_state(self) -> dict[str, Any]:
        """Return the persisted sync cursor state keyed by target name."""
        self.init()
        try:
            data = json.loads(self.sync_state_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def get_sync_cursor(self, target: str) -> int:
        """Return the last acknowledged cursor for a sync target."""
        state = self.get_sync_state()
        entry = state.get(target)
        if not isinstance(entry, dict):
            return 0
        cursor = entry.get("cursor", 0)
        return cursor if isinstance(cursor, int) and cursor >= 0 else 0

    def set_sync_cursor(
        self,
        target: str,
        cursor: int,
        *,
        endpoint: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Persist the last acknowledged cursor and metadata for a sync target."""
        if cursor < 0:
            raise ValueError("'cursor' must be greater than or equal to 0.")

        state = self.get_sync_state()
        entry = dict(state.get(target) or {})
        entry["cursor"] = cursor
        entry["updated_at"] = datetime.now(timezone.utc).isoformat()
        if endpoint is not None:
            entry["endpoint"] = endpoint
        if metadata:
            extra = dict(entry.get("metadata") or {})
            extra.update(metadata)
            entry["metadata"] = extra
        state[target] = entry
        self.sync_state_path.write_text(
            json.dumps(state, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        return entry

    def ingest_sync_batch(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Persist an incoming sync envelope and append records keyed by passport ID."""
        self.init()

        target = str(envelope["target"])
        source = str(envelope["source"])
        received_at = datetime.now(timezone.utc).isoformat()
        target_dir = self.sync_inbox_dir / self._safe_sync_target(target)
        target_dir.mkdir(parents=True, exist_ok=True)

        envelope_record = {
            "received_at": received_at,
            **envelope,
        }
        with self.sync_batches_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(envelope_record, sort_keys=True))
            handle.write("\n")

        stored_passport_ids: list[str] = []
        for item in envelope["items"]:
            passport_id = str(item["passport_id"])
            stored_passport_ids.append(passport_id)
            item_record = {
                "received_at": received_at,
                "source": source,
                "target": target,
                "after": envelope["after"],
                "cursor": envelope["cursor"],
                "has_more": envelope["has_more"],
                "item": item,
            }
            item_path = target_dir / f"{passport_id}.jsonl"
            with item_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(item_record, sort_keys=True))
                handle.write("\n")

        return {
            "status": "accepted",
            "source": source,
            "target": target,
            "cursor": envelope["cursor"],
            "accepted": len(envelope["items"]),
            "stored_passports": len(set(stored_passport_ids)),
            "received_at": received_at,
        }

    # ── Lineage ────────────────────────────────────────────────────────────────

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

    # ── Maintenance ────────────────────────────────────────────────────────────

    def rebuild_index(self) -> int:
        """Rebuild the SQLite index from JSON files. Returns count indexed."""
        records: list[tuple[dict[str, Any], str]] = []
        for path in (*self.models_dir.glob("*.json"), *self.agents_dir.glob("*.json")):
            try:
                data = json.loads(path.read_text())
                records.append((data, str(path.relative_to(self.root))))
            except Exception:
                pass
        with self._db() as db:
            db.rebuild_from_records(records)
        return len(records)

    def verify_passport(self, passport_id: str) -> dict[str, Any]:
        """Verify a stored passport's ID is consistent with its content."""
        passport = self.get(passport_id)
        if passport is None:
            return {"valid": False, "reason": "not_found", "stored_id": passport_id}
        return verify_passport_id(passport.to_dict())

    def _append_change(
        self,
        *,
        operation: str,
        passport_id: str,
        passport_type: str,
        json_path: str | None = None,
        document: dict[str, Any] | None = None,
    ) -> int:
        record: dict[str, Any] = {
            "cursor": self._load_outbox_cursor() + 1,
            "operation": operation,
            "passport_id": passport_id,
            "passport_type": passport_type,
            "changed_at": datetime.now(timezone.utc).isoformat(),
        }
        if json_path is not None:
            record["json_path"] = json_path
        if document is not None:
            record["document"] = document

        with self.outbox_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, sort_keys=True))
            handle.write("\n")

        self._outbox_cursor = record["cursor"]
        return record["cursor"]

    def _load_outbox_cursor(self) -> int:
        if self._outbox_cursor is not None:
            return self._outbox_cursor

        cursor = 0
        for record in self._read_outbox():
            value = record.get("cursor")
            if isinstance(value, int) and value > cursor:
                cursor = value
        self._outbox_cursor = cursor
        return cursor

    def _read_outbox(self) -> list[dict[str, Any]]:
        self.init()
        records: list[dict[str, Any]] = []
        with self.outbox_path.open("r", encoding="utf-8") as handle:
            for line in handle:
                raw = line.strip()
                if not raw:
                    continue
                try:
                    record = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    records.append(record)
        return records

    @staticmethod
    def _safe_sync_target(target: str) -> str:
        safe = "".join(char if char.isalnum() or char in ("-", "_", ".") else "-" for char in target)
        safe = safe.strip(".-")
        return safe or "default"
