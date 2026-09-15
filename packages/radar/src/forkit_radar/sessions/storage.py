"""Local session persistence reusing the existing private SQLite connection layer."""

from __future__ import annotations

import hashlib
import hmac
import os
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Literal
from uuid import uuid4

from pydantic import TypeAdapter

from ..contracts import Contract, Counter, Identifier
from ..discovery.safeio import directory
from ..identity.passports import now
from ..identity.storage import MAX_STORE_BYTES, EnrollmentStore, canonical
from ..jsonio import MAX_DOCUMENT_BYTES, ContractError, load_json
from ..lifecycle import session_operation
from .clock import stamp
from .details import Comparison, Delta, DetailedSnapshot, ReceiptV2, Selection, categories
from .details import complete as metadata_complete
from .details import difference as metadata_difference
from .evolution import SCHEMA as EVOLUTION_SCHEMA
from .evolution import append as append_evolution
from .evolution import prepare as prepare_evolution
from .inventory import capture, difference, select_project
from .metadata import capture as capture_metadata
from .metadata import unavailable as unavailable_metadata
from .models import Receipt, Snapshot, Started, elapsed


class ProjectLocator(Contract):
    path: str
    device: Counter
    inode: Counter


class SessionEntry(Contract):
    state: Literal["active", "completed", "interrupted"]
    started: Started


def checked_bytes(model) -> bytes:
    raw = canonical(model)
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ContractError("session_record_limit")
    load_json(raw, max_nodes=100_000)
    return raw


def _read_parsed(model, raw, data, *, encoder=None):
    try:
        record = model.model_validate(data)
        if (encoder(record) if encoder is not None else canonical(record)) != raw:
            raise ValueError
        return record
    except (ValueError, TypeError):
        raise ContractError("invalid_session_record") from None


def read(model, raw, *, encoder=None):
    try:
        data = load_json(raw, max_nodes=100_000)
    except (ValueError, TypeError):
        raise ContractError("invalid_session_record") from None
    return _read_parsed(model, raw, data, encoder=encoder)


def read_receipt(raw):
    data = load_json(raw, max_nodes=100_000)
    return _read_parsed(ReceiptV2 if data.get("schema_version") == "2.0" else Receipt, raw, data)


def read_snapshot(raw):
    data = load_json(raw, max_nodes=100_000)
    if data.get("schema_version") == "2.0":
        detailed = _read_parsed(DetailedSnapshot, raw, data)
        return detailed.files, detailed
    return _read_parsed(Snapshot, raw, data), None


def compare_endpoint(baseline, endpoint, *, baseline_id, skipped, recovered=False):
    if baseline is None:
        return Comparison(
            baseline_session_id=None,
            comparison="no_baseline",
            reason="no_comparable_receipt_in_last_100_project_sessions",
            skipped_sessions=skipped,
        )
    changes, unknown, complete = difference(baseline.files, endpoint.files)
    metadata = metadata_difference(baseline.metadata, endpoint.metadata)
    complete = (
        complete
        and metadata.status() == "complete"
        and metadata.passport_change != "unknown"
        and not recovered
    )
    return Comparison(
        baseline_session_id=baseline_id,
        comparison="complete" if complete else "partial",
        reason="includes_recovery_interval"
        if recovered
        else "same_project_and_selected_metadata_scope",
        skipped_sessions=skipped,
        file_changes=changes,
        unknown_count=unknown,
        metadata=metadata,
    )


def fit_receipt(receipt: ReceiptV2) -> ReceiptV2:
    """Bound repeated comparisons before sacrificing the current file receipt."""
    if len(canonical(receipt)) <= MAX_DOCUMENT_BYTES:
        return receipt
    data = receipt.model_dump()
    for field in ("since_previous", "between_sessions"):
        data[field] = Comparison(
            baseline_session_id=None,
            comparison="no_baseline",
            reason="comparison_record_limit",
            skipped_sessions=getattr(receipt, field).skipped_sessions,
        ).model_dump()
    fitted = ReceiptV2.model_validate(data)
    if len(canonical(fitted)) <= MAX_DOCUMENT_BYTES:
        return fitted
    delta = receipt.metadata.model_dump()
    delta["changes"] = []
    for coverage in delta["coverage"]:
        coverage.update(
            after="unavailable", comparison="partial", after_reason="receipt_detail_limit"
        )
    delta = Delta.model_validate(delta)
    data.update(
        metadata=delta,
        dependency_comparison=delta.status("dependencies"),
        configuration_comparison="partial",
        meaningful_categories=categories(receipt.file_changes, delta),
    )
    return ReceiptV2.model_validate(data)


class SessionStore(EnrollmentStore):
    database_name = "sessions.sqlite3"
    application_id = 0x46525353
    schema_version = 2
    legacy_schema = (
        "CREATE TABLE settings (name TEXT PRIMARY KEY, value BLOB NOT NULL)",
        "CREATE TABLE projects (project_id TEXT PRIMARY KEY, locator_token TEXT UNIQUE NOT NULL, locator BLOB NOT NULL)",
        "CREATE TABLE sessions (session_id TEXT PRIMARY KEY, project_id TEXT NOT NULL REFERENCES projects(project_id), state TEXT NOT NULL CHECK(state IN ('active','completed','interrupted')), started BLOB NOT NULL)",
        "CREATE UNIQUE INDEX one_active_session ON sessions(project_id) WHERE state='active'",
        "CREATE TABLE snapshots (session_id TEXT NOT NULL REFERENCES sessions(session_id), phase TEXT NOT NULL CHECK(phase IN ('before','after')), payload BLOB NOT NULL, PRIMARY KEY(session_id, phase))",
        "CREATE TABLE receipts (ordinal INTEGER PRIMARY KEY, session_id TEXT UNIQUE NOT NULL REFERENCES sessions(session_id), payload BLOB NOT NULL)",
    )
    schema = legacy_schema + EVOLUTION_SCHEMA

    @contextmanager
    def history_connection(self):
        """A consistent bounded in-memory copy releases live locks before rendering.

        The existing connection validates the private store/schema and bounds its
        size. SQLite copies its read transaction; all receipt/evolution checks
        still run on those exact bytes. No extra history file is written.
        """
        snapshot = sqlite3.connect(":memory:")
        try:
            with self._connect() as source:
                deadline = time.monotonic() + 5

                def progress(_status, _remaining, _total):
                    if time.monotonic() > deadline:
                        raise ContractError("history_snapshot_timeout")

                source.backup(snapshot, pages=128, progress=progress, sleep=0.005)
            snapshot.execute("PRAGMA trusted_schema=OFF")
            snapshot.execute("PRAGMA query_only=ON")
            deadline = time.monotonic() + 5
            snapshot.set_progress_handler(lambda: int(time.monotonic() > deadline), 1000)
            yield snapshot
        except sqlite3.Error:
            raise ContractError("history_snapshot_unavailable") from None
        finally:
            snapshot.close()

    def _check_schema(self, connection, version, app_id, schema, *, write):
        if (
            version == 1
            and app_id == self.application_id
            and {s[0] for s in schema} == set(self.legacy_schema)
        ):
            # Explicit versioned migration on the first write, in the caller's
            # transaction. Read-only use of old history makes no changes.
            if write:
                for statement in EVOLUTION_SCHEMA:
                    connection.execute(statement)
                connection.execute("PRAGMA user_version=2")
            return
        super()._check_schema(connection, version, app_id, schema, write=write)

    @staticmethod
    def _key(db) -> bytes:
        row = db.execute("SELECT value FROM settings WHERE name='locator_key'").fetchone()
        if row is None or type(row[0]) is not bytes or len(row[0]) != 32:
            raise ContractError("session_key_unavailable")
        return row[0]

    @staticmethod
    def _entry(row) -> SessionEntry:
        if row is None:
            raise ContractError("session_not_found")
        session_id, project_id, state, payload = row
        started = read(Started, payload)
        if (started.session_id, started.project_id) != (session_id, project_id):
            raise ContractError("invalid_session_projection")
        return SessionEntry(state=state, started=started)

    @session_operation
    def initialize(self):
        # A requested start waits for a concurrent creator's schema transaction
        # before reading active sessions. Readers must not mistake its temporary
        # zero-schema file for a permanently damaged store.
        with self._connect(write=True, create=True) as db:
            self._key(db)

    @session_operation
    def start(
        self,
        project: Path,
        *,
        tool: str,
        mode: str = "manual",
        selection: Selection | None = None,
        hook_identity: str | None = None,
    ) -> tuple[Started, Snapshot]:
        selection = Selection.model_validate(selection or Selection())
        project, identity = select_project(project)
        if self.root == project or project in self.root.parents:
            raise ContractError("session_store_must_be_outside_project")
        locator = ProjectLocator(path=str(project), device=identity[0], inode=identity[1])
        # Commit an empty valid store before capture. A failed first capture must
        # not leave a zero-schema SQLite file masquerading as corrupt history.
        self.initialize()
        with self._connect(write=True) as db:
            # Reserve a bounded finish (after snapshot + receipt + SQLite
            # overhead) for every active session before accepting a new one.
            page_size = db.execute("PRAGMA page_size").fetchone()[0]
            pages = db.execute("PRAGMA page_count").fetchone()[0]
            free = db.execute("PRAGMA freelist_count").fetchone()[0]
            available = MAX_STORE_BYTES - (pages - free) * page_size
            active = db.execute("SELECT COUNT(*) FROM sessions WHERE state='active'").fetchone()[0]
            if available < (active + 1) * 5_242_880 + MAX_DOCUMENT_BYTES + 131_072:
                raise ContractError("session_capacity_low_backup_or_compact")
            key = self._key(db)
            raw = checked_bytes(locator)
            token = hmac.new(key, b"forkit-session-project-v1\n" + raw, hashlib.sha256).hexdigest()
            row = db.execute(
                "SELECT project_id, locator FROM projects WHERE locator_token=?", (token,)
            ).fetchone()
            if row and row[1] != raw:
                raise ContractError("project_binding_conflict")
            project_id = row[0] if row else str(uuid4())
            if db.execute(
                "SELECT 1 FROM sessions WHERE project_id=? AND state='active'", (project_id,)
            ).fetchone():
                raise ContractError("active_session_exists_stop_or_recover_it")
            snapshot = capture(project, key)
            if not snapshot.inventory_complete:
                raise ContractError("complete_starting_inventory_required")
            if mode == "official_hook" and tool == "cursor":
                snapshot = snapshot.model_copy(
                    update={
                        "inventory_complete": False,
                        "reasons": tuple(
                            sorted(set(snapshot.reasons) | {"hook_start_not_blocking"})
                        ),
                    }
                )
            details = DetailedSnapshot(
                files=snapshot,
                selection=selection,
                metadata=capture_metadata(project, selection, key),
            )
            with directory(project) as descriptor:
                current = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) != identity:
                    raise ContractError("project_changed_during_capture")
            started = Started(
                session_id=str(uuid4()),
                project_id=project_id,
                tool=tool,
                capture_mode=mode,
                tool_basis="hook_reported" if mode == "official_hook" else "user_selected",
                started_at=now(),
                clock=stamp(key),
            )
            if mode == "official_hook":
                if not hook_identity:
                    raise ContractError("hook_identity_required")
                hook_token = self._hook_token(key, tool, hook_identity)
                db.execute(
                    "INSERT INTO settings VALUES (?, ?)", ("hook:" + started.session_id, hook_token)
                )
            if not row:
                db.execute("INSERT INTO projects VALUES (?, ?, ?)", (project_id, token, raw))
            db.execute(
                "INSERT INTO sessions VALUES (?, ?, 'active', ?)",
                (started.session_id, project_id, checked_bytes(started)),
            )
            db.execute(
                "INSERT INTO snapshots VALUES (?, 'before', ?)",
                (started.session_id, checked_bytes(details)),
            )
            return started, snapshot

    @session_operation
    def finish(self, session_id: str, *, outcome="manual_stop", exit_code=None) -> Receipt:
        TypeAdapter(Identifier).validate_python(session_id, strict=True)
        with self._connect() as db:
            entry_row = db.execute(
                "SELECT session_id, project_id, state, started FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            entry = self._entry(entry_row)
            if entry.state != "active":
                raise ContractError("session_already_finished")
            key = self._key(db)
            end_clock, finished_at = stamp(key), now()
            started = entry.started
            raw_locator = db.execute(
                "SELECT locator FROM projects WHERE project_id=?", (started.project_id,)
            ).fetchone()
            locator = read(ProjectLocator, raw_locator[0])
            baseline_row = db.execute(
                "SELECT payload FROM snapshots WHERE session_id=? AND phase='before'", (session_id,)
            ).fetchone()
            if baseline_row is None:
                raise ContractError("session_baseline_missing")
            before, before_details = read_snapshot(baseline_row[0])
        project = Path(locator.path)
        try:
            with directory(project) as descriptor:
                info = os.fstat(descriptor)
            if (info.st_dev, info.st_ino) != (locator.device, locator.inode):
                raise ValueError
            after = capture(project, key, previous=before)
            after_metadata = (
                capture_metadata(project, before_details.selection, key) if before_details else None
            )
            with directory(project) as descriptor:
                current = os.fstat(descriptor)
                if (current.st_dev, current.st_ino) != (locator.device, locator.inode):
                    raise ValueError
        except (OSError, ValueError):
            after = Snapshot(
                files=(),
                unknown_paths=(),
                excluded_count=0,
                inventory_complete=False,
                reasons=("project_unavailable_or_replaced",),
            )
            after_metadata = (
                unavailable_metadata(before_details.metadata, "project_unavailable_or_replaced")
                if before_details
                else None
            )
        stored_after = after
        if before_details is not None:
            stored_after = DetailedSnapshot(
                files=after, selection=before_details.selection, metadata=after_metadata
            )
            prepared_before = prepare_evolution(before_details)
            prepared_after = prepare_evolution(stored_after)
            delta = metadata_difference(before_details.metadata, after_metadata)
        stored_after_raw = checked_bytes(stored_after)
        changes, unknown_count, complete = difference(before, after)
        # File/metadata reads and pure preparation need no database write lock. Recheck the exact
        # starting inputs before one atomic commit; another finish or changed
        # baseline must never be overwritten with this prepared endpoint.
        with self._connect(write=True) as db:
            current_row = db.execute(
                "SELECT session_id, project_id, state, started FROM sessions WHERE session_id=?",
                (session_id,),
            ).fetchone()
            if self._entry(current_row).state != "active":
                raise ContractError("session_already_finished")
            if (
                current_row != entry_row
                or self._key(db) != key
                or db.execute(
                    "SELECT locator FROM projects WHERE project_id=?", (started.project_id,)
                ).fetchone()
                != raw_locator
                or db.execute(
                    "SELECT payload FROM snapshots WHERE session_id=? AND phase='before'",
                    (session_id,),
                ).fetchone()
                != baseline_row
            ):
                raise ContractError("session_changed_during_capture")
            elapsed_ms = elapsed(started.clock, end_clock)
            reasons = set(before.reasons) | set(after.reasons)
            if outcome == "recovered":
                elapsed_ms, complete = None, False
                reasons.add("session_end_unknown_changes_include_recovery_interval")
            if elapsed_ms is None:
                reasons.add("elapsed_time_unavailable")
            previous = db.execute(
                "SELECT receipts.session_id FROM receipts JOIN sessions USING(session_id) WHERE sessions.project_id=? ORDER BY receipts.ordinal DESC LIMIT 1",
                (started.project_id,),
            ).fetchone()
            receipt = Receipt(
                session_id=session_id,
                project_id=started.project_id,
                previous_session_id=previous[0] if previous else None,
                tool=started.tool,
                capture_mode=started.capture_mode,
                tool_basis=started.tool_basis,
                started_at=started.started_at,
                finished_at=finished_at,
                elapsed_ms=elapsed_ms,
                duration_basis="continuous_clock" if elapsed_ms is not None else "unknown",
                status="interrupted"
                if outcome in {"interrupted", "recovered", "launch_failed"}
                else "completed",
                exit_code=exit_code,
                outcome=outcome,
                comparison="complete" if complete else "partial",
                file_changes=changes,
                unknown_count=unknown_count,
                excluded_before=before.excluded_count,
                excluded_after=after.excluded_count,
                reasons=tuple(sorted(reasons)),
            )
            if before_details is not None:
                baseline_id, baseline, skipped = self._baseline(
                    db, started.project_id, before_details.selection
                )
                data = receipt.model_dump()
                data.update(
                    schema_version="2.0",
                    passport_id=after_metadata.passport.passport_id,
                    dependency_comparison=delta.status("dependencies"),
                    configuration_comparison="partial"
                    if any(
                        c.comparison == "partial" and c.category != "dependencies"
                        for c in delta.coverage
                    )
                    else "complete",
                    metadata=delta,
                    passport_before=before_details.metadata.passport,
                    passport_after=after_metadata.passport,
                    since_previous=compare_endpoint(
                        baseline,
                        stored_after,
                        baseline_id=baseline_id,
                        skipped=skipped,
                        recovered=outcome == "recovered",
                    ),
                    between_sessions=compare_endpoint(
                        baseline, before_details, baseline_id=baseline_id, skipped=skipped
                    ),
                    meaningful_categories=categories(changes, delta),
                )
                receipt = fit_receipt(ReceiptV2.model_validate(data))
            db.execute(
                "INSERT INTO snapshots VALUES (?, 'after', ?)",
                (session_id, stored_after_raw),
            )
            db.execute(
                "INSERT INTO receipts(session_id, payload) VALUES (?, ?)",
                (session_id, checked_bytes(receipt)),
            )
            if before_details is not None:
                append_evolution(db, receipt, prepared_before, prepared_after, key)
            db.execute(
                "UPDATE sessions SET state=? WHERE session_id=?", (receipt.status, session_id)
            )
            db.execute("DELETE FROM settings WHERE name=?", ("hook:" + session_id,))
            return receipt

    @staticmethod
    def _baseline(db, project_id, selection):
        rows = db.execute(
            "SELECT receipts.session_id, receipts.payload, snapshots.payload FROM receipts JOIN sessions USING(session_id) JOIN snapshots USING(session_id) WHERE sessions.project_id=? AND snapshots.phase='after' ORDER BY receipts.ordinal DESC LIMIT 100",
            (project_id,),
        ).fetchall()
        fallback = None
        for index, (session_id, raw_receipt, raw_snapshot) in enumerate(rows):
            receipt = read_receipt(raw_receipt)
            _files, snapshot = read_snapshot(raw_snapshot)
            if receipt.session_id != session_id or receipt.project_id != project_id:
                raise ContractError("invalid_receipt_projection")
            if snapshot is None or receipt.outcome == "recovered":
                continue
            # Explicit Passport selections may change, but they never establish
            # lineage. Agent manifest/registry locations must remain selected.
            if snapshot.selection.model_dump(exclude={"passport_id"}) != selection.model_dump(
                exclude={"passport_id"}
            ):
                continue
            if fallback is None:
                fallback = session_id, snapshot, index
            if (
                snapshot.files.inventory_complete
                and not snapshot.files.unknown_paths
                and metadata_complete(snapshot.metadata)
            ):
                return session_id, snapshot, index
        # Partial sources remain partial. A known intersection can still be
        # useful when no fully captured comparable endpoint exists.
        return fallback or (None, None, len(rows))

    @staticmethod
    def _hook_token(key, tool, identity):
        return hmac.new(
            key, ("forkit-hook-v1\n" + tool + "\n" + identity).encode(), hashlib.sha256
        ).digest()

    def matches_hook(self, entry, tool, identity):
        if entry.started.capture_mode != "official_hook" or entry.started.tool != tool:
            return False
        with self._connect() as db:
            row = db.execute(
                "SELECT value FROM settings WHERE name=?", ("hook:" + entry.started.session_id,)
            ).fetchone()
            return bool(
                row and hmac.compare_digest(row[0], self._hook_token(self._key(db), tool, identity))
            )

    def active_in(self, project: Path) -> SessionEntry | None:
        """Find only the exact selected project binding; never the latest global session."""
        project, identity = select_project(project)
        raw = checked_bytes(
            ProjectLocator(path=str(project), device=identity[0], inode=identity[1])
        )
        try:
            with self._connect() as db:
                token = hmac.new(
                    self._key(db), b"forkit-session-project-v1\n" + raw, hashlib.sha256
                ).hexdigest()
                binding = db.execute(
                    "SELECT project_id, locator FROM projects WHERE locator_token=?", (token,)
                ).fetchone()
                if binding is None:
                    return None
                if binding[1] != raw:
                    raise ContractError("project_binding_conflict")
                row = db.execute(
                    "SELECT session_id, project_id, state, started FROM sessions WHERE project_id=? AND state='active'",
                    (binding[0],),
                ).fetchone()
                return self._entry(row) if row else None
        except FileNotFoundError:
            return None

    def active(self) -> tuple[SessionEntry, ...]:
        try:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT session_id, project_id, state, started FROM sessions WHERE state='active' ORDER BY rowid DESC LIMIT 101"
                ).fetchall()
                if len(rows) > 100:
                    raise ContractError("session_listing_limit")
                return tuple(self._entry(row) for row in rows)
        except FileNotFoundError:
            return ()

    def history(self, *, limit: int = 20) -> tuple[Receipt, ...]:
        if type(limit) is not int or not 1 <= limit <= 100:
            raise ContractError("invalid_history_limit")
        try:
            with self._connect() as db:
                rows = db.execute(
                    "SELECT session_id, payload FROM receipts ORDER BY ordinal DESC LIMIT ?",
                    (limit,),
                ).fetchall()
                result = []
                for session_id, raw in rows:
                    receipt = read_receipt(raw)
                    if receipt.session_id != session_id:
                        raise ContractError("invalid_receipt_projection")
                    result.append(receipt)
                return tuple(result)
        except FileNotFoundError:
            return ()

    def receipt(self, session_id: str | None = None) -> Receipt:
        if session_id is None:
            rows = self.history(limit=1)
            if not rows:
                raise ContractError("no_local_receipts")
            return rows[0]
        TypeAdapter(Identifier).validate_python(session_id, strict=True)
        with self._connect() as db:
            row = db.execute(
                "SELECT payload FROM receipts WHERE session_id=?", (session_id,)
            ).fetchone()
            if row is None:
                raise ContractError("receipt_not_found")
            receipt = read_receipt(row[0])
            if receipt.session_id != session_id:
                raise ContractError("invalid_receipt_projection")
            return receipt
