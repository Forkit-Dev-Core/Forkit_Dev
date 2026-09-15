"""Private observed revisions, separate from Core identity and signed enrollment.

The chain checks retained local evidence, not AI authorship, ownership, or an
external trusted checkpoint. Restoring/modifying both data and heads is outside
its protection. No existing receipt or enrollment draft is rewritten.
"""

from __future__ import annotations

import hashlib
import hmac
import zlib
from functools import lru_cache
from typing import Literal

from ..contracts import Contract, Digest, Identifier, Sequence
from ..identity.storage import canonical
from ..jsonio import MAX_DOCUMENT_BYTES, ContractError
from .details import DetailedSnapshot, Metadata, ReceiptV2
from .details import difference as metadata_difference
from .inventory import difference as file_difference
from .meaningful import POLICY, ChangeCounts, changes, counts
from .models import Snapshot

PROFILE = "session-observed-state-v1"
MAX_HISTORY = 10_000
SCHEMA = (
    "CREATE TABLE observed_revisions (project_id TEXT NOT NULL REFERENCES projects(project_id), scope_token TEXT NOT NULL, digest TEXT NOT NULL, payload BLOB NOT NULL, PRIMARY KEY(project_id, scope_token, digest))",
    "CREATE TABLE session_evolution (session_id TEXT PRIMARY KEY REFERENCES receipts(session_id), project_id TEXT NOT NULL REFERENCES projects(project_id), scope_token TEXT NOT NULL, digest TEXT UNIQUE NOT NULL, payload BLOB NOT NULL)",
    "CREATE TABLE evolution_heads (project_id TEXT NOT NULL REFERENCES projects(project_id), scope_token TEXT NOT NULL, session_id TEXT NOT NULL REFERENCES session_evolution(session_id), digest TEXT NOT NULL, PRIMARY KEY(project_id, scope_token))",
)


class Revision(Contract):
    profile: Literal["session-observed-state-v1"] = PROFILE
    files: Snapshot
    metadata: Metadata


class Event(Contract):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["local_session_evolution"] = "local_session_evolution"
    association_basis: Literal["explicit_declared_association"] = "explicit_declared_association"
    continuity_basis: Literal["local_project_and_selected_scope"] = "local_project_and_selected_scope"
    authentication: Literal["unsigned_local_record"] = "unsigned_local_record"
    session_id: Identifier
    project_id: Identifier
    scope_token: Digest
    sequence: Sequence
    receipt_digest: Digest
    before_revision: Digest
    after_revision: Digest
    previous_session_id: Identifier | None
    previous_event_digest: Digest | None
    previous_after_revision: Digest | None
    previous_project_session_id: Identifier | None
    counting_policy: Literal["session-meaningful-changes-v1"] = POLICY
    during_counts: ChangeCounts
    between_counts: ChangeCounts | None


def digest(domain: str, raw: bytes) -> str:
    return hashlib.sha256(domain.encode("ascii") + b"\n" + raw).hexdigest()


def normalized(snapshot: DetailedSnapshot) -> Revision:
    # Scope/completeness and supported state are comparable; read diagnostics,
    # excluded-file totals, locators and ordering are not content changes.
    files = snapshot.files.model_dump()
    files.update(
        files=sorted(files["files"], key=lambda f: f["path"]),
        unknown_paths=sorted(files["unknown_paths"]),
        excluded_count=0,
        reasons=(),
    )
    metadata = snapshot.metadata.model_dump()
    for source in metadata["sources"]:
        source["facts"] = sorted(source["facts"], key=lambda f: f["key"])
        source["reason"] = "normalized_source_state"
    metadata["sources"] = sorted(metadata["sources"], key=lambda s: s["key"])
    metadata["passport"]["reason"] = "captured_core_check"
    return Revision(files=Snapshot.model_validate(files), metadata=Metadata.model_validate(metadata))


def unpack(raw: bytes) -> bytes:
    # A corrupt/compressed bomb must not allocate unbounded memory. Concatenated
    # streams, trailing bytes and truncation are also rejected.
    if type(raw) is not bytes or len(raw) > MAX_DOCUMENT_BYTES + 1024:
        raise ContractError("invalid_revision_compression")
    try:
        decoder = zlib.decompressobj()
        payload = decoder.decompress(raw, MAX_DOCUMENT_BYTES + 1)
        if (
            len(payload) > MAX_DOCUMENT_BYTES
            or not decoder.eof
            or decoder.unused_data
            or decoder.unconsumed_tail
        ):
            raise ValueError
        return payload
    except (zlib.error, ValueError):
        raise ContractError("invalid_revision_compression") from None


def _store_revision(db, project_id, scope, snapshot):
    from .storage import checked_bytes

    revision = normalized(snapshot)
    raw = checked_bytes(revision)
    identity = digest("forkit-session-revision-v1", raw)
    previous = db.execute(
        "SELECT payload FROM observed_revisions WHERE project_id=? AND scope_token=? AND digest=?",
        (project_id, scope, identity),
    ).fetchone()
    if previous:
        if unpack(previous[0]) != raw:
            raise ContractError("revision_content_conflict")
    else:
        db.execute(
            "INSERT INTO observed_revisions VALUES (?, ?, ?, ?)",
            (project_id, scope, identity, zlib.compress(raw)),
        )
    return identity


def read_event(row):
    from .storage import read

    if row is None:
        raise ContractError("evolution_record_missing")
    session_id, project_id, scope, identity, raw = row
    event = read(Event, raw)
    if (
        (event.session_id, event.project_id, event.scope_token) != (session_id, project_id, scope)
        or digest("forkit-session-event-v1", raw) != identity
    ):
        raise ContractError("evolution_record_mismatch")
    return event, identity


def append(db, receipt: ReceiptV2, before: DetailedSnapshot, after: DetailedSnapshot, key: bytes):
    from .storage import checked_bytes, read

    scope = hmac.new(
        key,
        b"forkit-session-evolution-scope-v1\n"
        + canonical(before.selection.model_copy(update={"passport_id": None})),
        hashlib.sha256,
    ).hexdigest()
    head = db.execute(
        "SELECT session_id, digest FROM evolution_heads WHERE project_id=? AND scope_token=?",
        (receipt.project_id, scope),
    ).fetchone()
    prior, prior_digest = None, None
    if head:
        prior, prior_digest = read_event(db.execute(
            "SELECT session_id, project_id, scope_token, digest, payload FROM session_evolution WHERE session_id=?",
            (head[0],),
        ).fetchone())
        if prior_digest != head[1] or (prior.project_id, prior.scope_token) != (receipt.project_id, scope):
            raise ContractError("evolution_head_mismatch")
    count = db.execute(
        "SELECT COUNT(*) FROM session_evolution WHERE project_id=? AND scope_token=?",
        (receipt.project_id, scope),
    ).fetchone()[0]
    if count != (prior.sequence if prior else 0):
        raise ContractError("evolution_chain_gap")
    left, right = normalized(before), normalized(after)
    during_counts = interval_counts(left, right)
    between_counts = None
    if prior and receipt.previous_session_id == prior.session_id:
        previous = db.execute(
            "SELECT payload FROM observed_revisions WHERE project_id=? AND scope_token=? AND digest=?",
            (receipt.project_id, scope, prior.after_revision),
        ).fetchone()
        if previous is None:
            raise ContractError("revision_missing")
        previous_raw = unpack(previous[0])
        if digest("forkit-session-revision-v1", previous_raw) != prior.after_revision:
            raise ContractError("revision_digest_mismatch")
        between_counts = interval_counts(read(Revision, previous_raw), left)
    event = Event(
        session_id=receipt.session_id, project_id=receipt.project_id, scope_token=scope,
        sequence=count + 1,
        receipt_digest=digest("forkit-session-receipt-v1", checked_bytes(receipt)),
        before_revision=_store_revision(db, receipt.project_id, scope, before),
        after_revision=_store_revision(db, receipt.project_id, scope, after),
        previous_session_id=prior.session_id if prior else None,
        previous_event_digest=prior_digest,
        previous_after_revision=prior.after_revision if prior else None,
        previous_project_session_id=receipt.previous_session_id,
        during_counts=during_counts, between_counts=between_counts,
    )
    raw = checked_bytes(event)
    identity = digest("forkit-session-event-v1", raw)
    db.execute("INSERT INTO session_evolution VALUES (?, ?, ?, ?, ?)", (
        event.session_id, event.project_id, scope, identity, raw,
    ))
    db.execute(
        "INSERT INTO evolution_heads VALUES (?, ?, ?, ?) ON CONFLICT(project_id, scope_token) DO UPDATE SET session_id=excluded.session_id, digest=excluded.digest",
        (event.project_id, scope, event.session_id, identity),
    )


def verify(db):
    """Yield each receipt with checked endpoints; one bounded DB read snapshot.

    A bad evolution record is visible alongside the still-readable receipt. It
    invalidates dependent links rather than turning them into fresh genesis.
    """
    from .storage import read, read_receipt

    count = db.execute("SELECT COUNT(*) FROM receipts").fetchone()[0]
    if count > MAX_HISTORY:
        raise ContractError("evolution_history_limit")
    upgraded = db.execute("PRAGMA user_version").fetchone()[0] == 2
    events, heads, last = {}, {}, {}
    if upgraded:
        rows = db.execute("SELECT session_id, project_id, scope_token, digest, payload FROM session_evolution").fetchall()
        if len(rows) > MAX_HISTORY:
            raise ContractError("evolution_history_limit")
        events = {row[0]: row for row in rows}
        heads = {(p, s): (sid, d) for p, s, sid, d in db.execute("SELECT * FROM evolution_heads")}
        for sid, p, s, d in db.execute("SELECT e.session_id, e.project_id, e.scope_token, e.digest FROM session_evolution e JOIN receipts r USING(session_id) ORDER BY r.ordinal"):
            last[p, s] = (sid, d)

    @lru_cache(maxsize=16)
    def revision(project, scope, identity):
        row = db.execute("SELECT payload FROM observed_revisions WHERE project_id=? AND scope_token=? AND digest=?", (project, scope, identity)).fetchone()
        if row is None:
            raise ContractError("revision_missing")
        raw = unpack(row[0])
        if digest("forkit-session-revision-v1", raw) != identity:
            raise ContractError("revision_digest_mismatch")
        result = read(Revision, raw)
        # Enforce the normalization profile, including semantic set ordering.
        if normalized(DetailedSnapshot(files=result.files, metadata=result.metadata, selection={} )) != result:
            raise ContractError("revision_not_normalized")
        return result

    prior_scope, prior_project = {}, {}
    for sid, pid, state, started_raw, raw in db.execute(
        "SELECT r.session_id, s.project_id, s.state, s.started, r.payload FROM receipts r JOIN sessions s USING(session_id) ORDER BY r.ordinal"
    ):
        receipt = read_receipt(raw)
        from .models import Started
        started = read(Started, started_raw)
        if (receipt.session_id, receipt.project_id, receipt.status) != (sid, pid, state) or (
            started.session_id, started.project_id, started.tool, started.capture_mode, started.started_at
        ) != (sid, pid, receipt.tool, receipt.capture_mode, receipt.started_at):
            raise ContractError("invalid_receipt_projection")
        result = {"status": "unavailable", "reason": "legacy_receipt_no_retained_evolution", "event": None, "before": None, "after": None, "gap_before": None}
        row = events.get(sid)
        if row:
            scope_key = (row[1], row[2])
            previous = prior_scope.get(scope_key)
            valid = False
            try:
                event, identity = read_event(row)
                result["event"] = event
                expected_previous = (previous[0], previous[1], previous[2], previous[3] + 1) if previous else (None, None, None, 1)
                if (
                    (event.project_id, event.session_id) != (pid, sid)
                    or
                    (event.previous_session_id, event.previous_event_digest, event.previous_after_revision, event.sequence) != expected_previous
                    or previous and not previous[4]
                    or heads.get(scope_key) != last.get(scope_key)
                    or event.previous_project_session_id != receipt.previous_session_id
                    or receipt.previous_session_id != prior_project.get(pid)
                ):
                    raise ContractError("evolution_chain_gap")
                if event.receipt_digest != digest("forkit-session-receipt-v1", raw):
                    raise ContractError("receipt_digest_mismatch")
                before = revision(pid, event.scope_token, event.before_revision)
                after = revision(pid, event.scope_token, event.after_revision)
                if not isinstance(receipt, ReceiptV2):
                    raise ContractError("evolution_requires_detailed_receipt")
                for recorded, captured in ((before.metadata.passport, receipt.passport_before), (after.metadata.passport, receipt.passport_after)):
                    if recorded.model_dump(exclude={"reason"}) != captured.model_dump(exclude={"reason"}):
                        raise ContractError("passport_endpoint_mismatch")
                file_changes, unknown, complete = file_difference(before.files, after.files)
                if file_changes != receipt.file_changes or unknown != receipt.unknown_count or (
                    receipt.outcome != "recovered" and receipt.comparison != ("complete" if complete else "partial")
                ):
                    raise ContractError("file_endpoint_mismatch")
                delta = metadata_difference(before.metadata, after.metadata)
                reduced = any(c.after_reason == "receipt_detail_limit" for c in receipt.metadata.coverage)
                if delta.passport_change != receipt.metadata.passport_change or not reduced and (
                    delta.changes != receipt.metadata.changes
                    or [c.model_dump(exclude={"before_reason", "after_reason"}) for c in delta.coverage]
                    != [c.model_dump(exclude={"before_reason", "after_reason"}) for c in receipt.metadata.coverage]
                ):
                    raise ContractError("metadata_endpoint_mismatch")
                if interval_counts(before, after) != event.during_counts:
                    raise ContractError("evolution_count_mismatch")
                result.update(status="consistent", reason="retained_local_evidence_checked", before=before, after=after)
                if previous and receipt.previous_session_id == previous[0]:
                    result["gap_before"] = revision(pid, event.scope_token, event.previous_after_revision)
                    if interval_counts(result["gap_before"], before) != event.between_counts:
                        raise ContractError("evolution_count_mismatch")
                elif event.between_counts is not None:
                    raise ContractError("unexpected_gap_counts")
                valid = True
            except (ValueError, TypeError) as error:
                if str(error) in {"evolution_count_mismatch", "unexpected_gap_counts"}:
                    result["event"] = None
                result.update(status="broken", reason="missing_or_inconsistent_local_evidence", before=None, after=None, gap_before=None)
            # Retain the expected predecessor even when its content is broken.
            event = result["event"]
            prior_scope[scope_key] = (sid, row[3], event.after_revision if event else None, event.sequence if event else 0, valid)
        elif upgraded:
            # An absent event with a head pointing to it cannot be mistaken for
            # old data. Descendants will also fail their predecessor checks.
            if any(head[0] == sid for head in heads.values()):
                result.update(status="broken", reason="evolution_record_missing")
        prior_project[pid] = sid
        yield receipt, result


def interval(before: Revision, after: Revision):
    changes, unknown, complete = file_difference(before.files, after.files)
    delta = metadata_difference(before.metadata, after.metadata)
    return changes, delta, unknown, complete


def interval_counts(before: Revision, after: Revision):
    files, delta, _unknown, _complete = interval(before, after)
    return ChangeCounts(**counts(changes(files, delta, before.metadata.passport, after.metadata.passport)))
