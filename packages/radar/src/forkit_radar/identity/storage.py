"""Private, serialized SQLite drafts; no signing authority or accepted identities.

Filesystem permissions contain ordinary cross-user access. They do not resist a
compromised user/OS or copied/rolled-back storage. Full history/backup is S11.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
import stat
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from uuid import uuid4

import rfc8785
from pydantic import TypeAdapter

from ..contracts import Identifier
from ..discovery.safeio import directory
from ..jsonio import ContractError, load_json
from .enrollment import EnrollmentDraft, EnrollmentEntry, EnrollmentPreview, Locator, select_source
from .passports import now

APPLICATION_ID = 0x46524452  # Local application marker, not a registered global ID.
SCHEMA_VERSION = 1
MAX_STORE_BYTES = 67_108_864
_CONNECTION_LOCK = threading.RLock()
SCHEMA = (
    "CREATE TABLE settings (name TEXT PRIMARY KEY, value BLOB NOT NULL)",
    "CREATE TABLE sources (source_slot_id TEXT PRIMARY KEY, locator_token TEXT UNIQUE NOT NULL, locator BLOB NOT NULL)",
    "CREATE TABLE drafts (proposal_id TEXT PRIMARY KEY, logical_id TEXT UNIQUE NOT NULL, source_slot_id TEXT NOT NULL REFERENCES sources(source_slot_id), state TEXT NOT NULL CHECK(state IN ('pending','cancelled')), payload BLOB NOT NULL)",
    "CREATE UNIQUE INDEX one_pending_source ON drafts(source_slot_id) WHERE state='pending'",
    "CREATE TABLE draft_events (event_id TEXT PRIMARY KEY, proposal_id TEXT NOT NULL REFERENCES drafts(proposal_id), kind TEXT NOT NULL CHECK(kind IN ('proposed','cancelled')), recorded_at TEXT NOT NULL)",
)


def canonical(model) -> bytes:
    return rfc8785.dumps(model.model_dump(mode="json"))


def _private(info, *, is_directory=False):
    proper = stat.S_ISDIR(info.st_mode) if is_directory else stat.S_ISREG(info.st_mode)
    if (
        not proper
        or info.st_uid != os.geteuid()
        or stat.S_IMODE(info.st_mode) != (0o700 if is_directory else 0o600)
    ):
        raise ContractError("private_store_permissions_required")
    if not is_directory and (info.st_nlink != 1 or info.st_size > MAX_STORE_BYTES):
        raise ContractError("unsafe_store_file")


def write_new(path: Path, raw: bytes):
    """Publish a complete Core document with exclusive creation, mode 0600."""
    path = path.absolute()
    with directory(path.parent) as parent:
        temp = f".radar-{uuid4()}.tmp"
        descriptor = os.open(
            temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600, dir_fd=parent
        )
        try:
            with os.fdopen(descriptor, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            # link is exclusive; an existing destination is never overwritten.
            os.link(temp, path.name, src_dir_fd=parent, dst_dir_fd=parent, follow_symlinks=False)
        finally:
            os.unlink(temp, dir_fd=parent)
        os.fsync(parent)


class EnrollmentStore:
    # Session storage shares these hardened connection mechanics, while keeping
    # its schema and file separate from immutable enrollment drafts.
    database_name = "enrollment.sqlite3"
    schema = SCHEMA
    schema_version = SCHEMA_VERSION
    application_id = APPLICATION_ID

    def __init__(self, root: Path):
        self.root = root.absolute()

    def _check_schema(self, connection, version, app_id, schema, *, write):
        if (
            version != self.schema_version
            or app_id != self.application_id
            or {s[0] for s in schema} != set(self.schema)
        ):
            raise ContractError("unsupported_store_schema")

    @contextmanager
    def _connect(self, *, write=False, create=False):
        # Serialize our connections in-process; SQLite BEGIN IMMEDIATE serializes
        # writers across processes. Never carry a connection across fork().
        if not _CONNECTION_LOCK.acquire(timeout=2):
            raise ContractError("store_busy")
        try:
            with self._connection(write=write, create=create) as connection:
                yield connection
        finally:
            _CONNECTION_LOCK.release()

    @contextmanager
    def _connection(self, *, write=False, create=False):
        if os.name != "posix":
            raise ContractError("unsupported_store_platform")
        with directory(self.root.parent) as parent:
            if create:
                try:
                    os.mkdir(self.root.name, mode=0o700, dir_fd=parent)
                except FileExistsError:
                    pass
            with directory(self.root) as root_fd:
                _private(os.fstat(root_fd), is_directory=True)
                db_name = self.database_name
                if create:
                    try:
                        fd = os.open(
                            db_name,
                            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
                            0o600,
                            dir_fd=root_fd,
                        )
                    except FileExistsError:
                        pass
                    else:
                        os.close(fd)
                # Do not open/close an existing DB through a non-SQLite handle:
                # close() can release this process's other POSIX advisory locks.
                original = os.stat(db_name, dir_fd=root_fd, follow_symlinks=False)
                _private(original)
                connection = None
                try:
                    for suffix in ("-journal", "-wal", "-shm"):
                        try:
                            _private(
                                os.stat(db_name + suffix, dir_fd=root_fd, follow_symlinks=False)
                            )
                        except FileNotFoundError:
                            pass
                    db_path = self.root / db_name
                    connection = sqlite3.connect(
                        db_path.as_uri() + ("?mode=rw" if write else "?mode=ro"),
                        uri=True,
                        timeout=2,
                        isolation_level=None,
                    )
                    connection.execute("PRAGMA trusted_schema=OFF")
                    connection.execute("PRAGMA foreign_keys=ON")
                    connection.execute("PRAGMA synchronous=FULL")
                    connection.execute("PRAGMA busy_timeout=2000")
                    if write:
                        page_size = connection.execute("PRAGMA page_size").fetchone()[0]
                        # Enforce the read boundary at write time. A full write
                        # must roll back, not strand readable history above it.
                        limit = MAX_STORE_BYTES // page_size
                        actual = connection.execute(f"PRAGMA max_page_count={limit}").fetchone()[0]
                        if actual > limit:
                            raise ContractError("store_capacity_exhausted")
                    if connection.execute("PRAGMA journal_mode").fetchone()[0] != "delete":
                        raise ContractError("unsupported_store_journal")
                    deadline = time.monotonic() + 5
                    connection.set_progress_handler(
                        lambda: 1 if time.monotonic() > deadline else 0, 1000
                    )
                    connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
                    version = connection.execute("PRAGMA user_version").fetchone()[0]
                    app_id = connection.execute("PRAGMA application_id").fetchone()[0]
                    schema = connection.execute(
                        "SELECT sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY name"
                    ).fetchall()
                    if not schema and version == 0 and app_id == 0 and create:
                        for statement in self.schema:
                            connection.execute(statement)
                        connection.execute(f"PRAGMA application_id={self.application_id}")
                        connection.execute(f"PRAGMA user_version={self.schema_version}")
                        # Locator pseudonymization only: not an authority/signing key.
                        connection.execute(
                            "INSERT INTO settings VALUES ('locator_key', ?)",
                            (secrets.token_bytes(32),),
                        )
                    else:
                        self._check_schema(connection, version, app_id, schema, write=write)
                    if (
                        connection.execute("PRAGMA quick_check(1)").fetchone()[0] != "ok"
                        or connection.execute("PRAGMA foreign_key_check").fetchone()
                    ):
                        raise ContractError("invalid_store")
                    before = original
                    located = os.stat(db_name, dir_fd=root_fd, follow_symlinks=False)
                    if (before.st_dev, before.st_ino) != (located.st_dev, located.st_ino):
                        raise ContractError("store_replaced")
                    yield connection
                    current_root = os.stat(self.root.name, dir_fd=parent, follow_symlinks=False)
                    opened_root = os.fstat(root_fd)
                    located = os.stat(db_name, dir_fd=root_fd, follow_symlinks=False)
                    if (current_root.st_dev, current_root.st_ino) != (
                        opened_root.st_dev,
                        opened_root.st_ino,
                    ) or (before.st_dev, before.st_ino) != (located.st_dev, located.st_ino):
                        raise ContractError("store_replaced")
                    connection.commit()
                except sqlite3.Error as error:
                    if getattr(error, "sqlite_errorcode", -1) == getattr(sqlite3, "SQLITE_FULL", 13) or str(error) == "database or disk is full":
                        raise ContractError("store_capacity_exhausted") from None
                    raise ContractError("store_unavailable_or_invalid") from None
                finally:
                    if connection is not None:
                        connection.close()  # Rolls back any unfinished transaction.

    @staticmethod
    def _entry(row) -> EnrollmentEntry:
        if row is None:
            raise ContractError("proposal_not_found")
        proposal_id, logical_id, slot, state, raw = row
        try:
            draft = EnrollmentDraft.model_validate(load_json(raw))
            if canonical(draft) != raw or (
                draft.proposal_id,
                draft.reserved_logical_agent_id,
                draft.source_slot_id,
            ) != (proposal_id, logical_id, slot):
                raise ValueError
            return EnrollmentEntry(state=state, draft=draft)
        except (ValueError, TypeError):
            raise ContractError("invalid_stored_proposal") from None

    def propose(self, locator: Locator, preview: EnrollmentPreview) -> EnrollmentEntry:
        locator = Locator.model_validate(locator)
        preview = EnrollmentPreview.model_validate(preview)
        _, current = select_source(
            agent_file=Path(locator.path) if locator.adapter == "agent-manifest" else None,
            project=Path(locator.path).parent if locator.adapter == "langgraph" else None,
            graph_key=locator.selector,
        )
        fields = {"provisional_component_key"}
        if current.model_dump(exclude=fields) != preview.manifest.model_dump(exclude=fields):
            raise ContractError("source_changed_since_preview")
        if preview.association.state in {"ambiguous", "conflicted"}:
            raise ContractError("resolve_association_before_proposal")
        with self._connect(write=True, create=True) as db:
            key = db.execute("SELECT value FROM settings WHERE name='locator_key'").fetchone()
            if key is None or type(key[0]) is not bytes or len(key[0]) != 32:
                raise ContractError("locator_key_unavailable")
            raw_locator = canonical(locator)
            token = hmac.new(
                key[0], b"forkit-radar-private-locator-v1\n" + raw_locator, hashlib.sha256
            ).hexdigest()
            row = db.execute(
                "SELECT source_slot_id, locator FROM sources WHERE locator_token=?", (token,)
            ).fetchone()
            if row and row[1] != raw_locator:
                raise ContractError("source_binding_conflict")
            slot = row[0] if row else str(uuid4())
            if db.execute(
                "SELECT 1 FROM drafts WHERE source_slot_id=? AND state='pending'", (slot,)
            ).fetchone():
                raise ContractError("pending_proposal_exists")
            if not row:
                db.execute("INSERT INTO sources VALUES (?, ?, ?)", (slot, token, raw_locator))
            draft = EnrollmentDraft(
                schema_version="1.0",
                proposal_id=str(uuid4()),
                reserved_logical_agent_id=str(uuid4()),
                source_slot_id=slot,
                created_at=now(),
                preview=preview,
            )
            db.execute(
                "INSERT INTO drafts VALUES (?, ?, ?, 'pending', ?)",
                (draft.proposal_id, draft.reserved_logical_agent_id, slot, canonical(draft)),
            )
            db.execute(
                "INSERT INTO draft_events VALUES (?, ?, 'proposed', ?)",
                (str(uuid4()), draft.proposal_id, now()),
            )
            return EnrollmentEntry(state="pending", draft=draft)

    def list(self) -> tuple[EnrollmentEntry, ...]:
        with self._connect() as db:
            rows = db.execute(
                "SELECT proposal_id, logical_id, source_slot_id, state, payload FROM drafts ORDER BY proposal_id LIMIT 129"
            ).fetchall()
            if len(rows) > 128:
                raise ContractError("proposal_listing_limit")
            return tuple(self._entry(row) for row in rows)

    def get(self, proposal_id: str) -> EnrollmentEntry:
        TypeAdapter(Identifier).validate_python(proposal_id, strict=True)
        with self._connect() as db:
            return self._entry(
                db.execute(
                    "SELECT proposal_id, logical_id, source_slot_id, state, payload FROM drafts WHERE proposal_id=?",
                    (proposal_id,),
                ).fetchone()
            )

    def cancel(self, proposal_id: str) -> EnrollmentEntry:
        TypeAdapter(Identifier).validate_python(proposal_id, strict=True)
        with self._connect(write=True) as db:
            entry = self._entry(
                db.execute(
                    "SELECT proposal_id, logical_id, source_slot_id, state, payload FROM drafts WHERE proposal_id=?",
                    (proposal_id,),
                ).fetchone()
            )
            if entry.state != "pending":
                raise ContractError("proposal_already_cancelled")
            db.execute("UPDATE drafts SET state='cancelled' WHERE proposal_id=?", (proposal_id,))
            db.execute(
                "INSERT INTO draft_events VALUES (?, ?, 'cancelled', ?)",
                (str(uuid4()), proposal_id, now()),
            )
            return EnrollmentEntry(state="cancelled", draft=entry.draft)
