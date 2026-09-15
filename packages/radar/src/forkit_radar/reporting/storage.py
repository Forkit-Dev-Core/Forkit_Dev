"""Private consent/credential state and count-only CLI operation journal."""
from __future__ import annotations

import secrets
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from rfc8785 import dumps

from ..identity.storage import EnrollmentStore
from ..jsonio import ContractError, load_json
from .contracts import Discovery


def today():
    return datetime.now(timezone.utc).date().isoformat()


class ReportingStore(EnrollmentStore):
    database_name = "reporting.sqlite3"
    application_id = 0x46524D54
    schema_version = 1
    schema = (
        "CREATE TABLE settings (name TEXT PRIMARY KEY, value BLOB NOT NULL)",
        "CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL)",
        "CREATE TABLE operations (operation_id TEXT PRIMARY KEY, day TEXT NOT NULL, kind TEXT NOT NULL CHECK(kind IN ('scan','passport')), payload BLOB NOT NULL)",
    )

    @staticmethod
    def _profile(db):
        row = db.execute("SELECT payload FROM profile WHERE id=1").fetchone()
        if row is None:
            raise ContractError("reporting_profile_missing")
        from .client import validate_profile
        return validate_profile(load_json(row[0]))

    @staticmethod
    def _save(db, profile):
        db.execute("UPDATE profile SET payload=? WHERE id=1", (dumps(profile),))

    def status(self):
        try:
            with self._connect() as db:
                p = self._profile(db)
                return {k: p[k] for k in ("state", "endpoint", "surface_id", "last_sent_sequence", "journal_complete")}
        except FileNotFoundError:
            return {"state": "disabled", "endpoint": None, "surface_id": None, "last_sent_sequence": 0, "journal_complete": True}

    def enable(self, endpoint, allow_local=False):
        from .client import checked_endpoint
        endpoint = checked_endpoint(endpoint, allow_local=allow_local)
        with self._connect(write=True, create=True) as db:
            row = db.execute("SELECT payload FROM profile WHERE id=1").fetchone()
            if row:
                p = self._profile(db)
                if p["state"] != "withdrawn":
                    if (p["endpoint"], p["allow_local"]) != (endpoint, allow_local):
                        raise ContractError("withdraw_before_changing_collector")
                    p["state"] = "enabled"
                    self._save(db, p)
                    return
            p = dict(state="enabled", endpoint=endpoint, allow_local=allow_local,
                     surface_id=str(uuid4()), credential=secrets.token_hex(32),
                     sequence=0, last_sent_sequence=0, journal_complete=True)
            db.execute("INSERT INTO profile VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload", (dumps(p),))
            if row:
                db.execute("DELETE FROM operations")

    def disable(self):
        if self.status()["surface_id"] is None:
            return
        with self._connect(write=True) as db:
            p = self._profile(db)
            if p["state"] != "withdrawn":
                p["state"] = "disabled"
                self._save(db, p)

    def operation(self, kind, payload, *, identity=None, observed_on=None):
        if self.status()["state"] != "enabled":
            return
        with self._connect(write=True) as db:
            p = self._profile(db)
            if p["state"] != "enabled":
                return
            if db.execute("SELECT COUNT(*) FROM operations").fetchone()[0] >= 10_000:
                p["journal_complete"] = False
                self._save(db, p)
                return
            db.execute("INSERT OR IGNORE INTO operations VALUES (?, ?, ?, ?)",
                       (identity or str(uuid4()), observed_on or today(), kind, dumps(payload)))


def note_scan(root, report):
    from ..discovery.types import scope_keys

    store = ReportingStore(root)
    if store.status()["state"] != "enabled":
        return
    groups = {"models": ("ollama",), "agents": ("langgraph", "agent-manifest"),
              "mcp_servers": ("codex-mcp", "cursor-mcp"), "applications_and_processes": ("applications", "processes")}
    counts = {}
    for category, detectors in groups.items():
        scopes = {scope for detector in detectors for scope in scope_keys(detector)}
        selected = [s for s in report.sources if s.scope in scopes]
        # Unselected/failed categories are unknown, never reported as zero.
        counts[category] = sum(f.observation.manifest is not None for s in selected for f in s.findings) if selected and all(s.status in {"complete", "missing"} for s in selected) else None
    successful = bool(report.sources) and all(s.status in {"complete", "missing"} for s in report.sources)
    discovery = Discovery(observed_on=today(), partial=not successful, **counts)
    store.operation("scan", {"successful": successful, "discovery": discovery.model_dump()})


def note_passport(root, passport_id):
    # Deduplicate exact Core IDs locally. Never transmit this identifier/hash.
    if not isinstance(passport_id, str) or len(passport_id) != 64:
        raise ContractError("invalid_created_passport")
    ReportingStore(root).operation("passport", {}, identity="passport:" + passport_id)


def safely_note(kind, *args, root=None):
    # Optional reporting cannot break a successful local action. No network here.
    import sys
    try:
        selected = root or Path.home() / ".forkit-radar"
        (note_scan if kind == "scan" else note_passport)(selected, *args)
    except Exception:
        print("Local result saved. Optional aggregate journal unavailable; reporting counts may be incomplete.", file=sys.stderr)
