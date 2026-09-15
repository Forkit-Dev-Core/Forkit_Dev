"""Project local evidence into four UTC calendar weeks of allowlisted counts."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from ..jsonio import ContractError, load_json
from ..sessions.evolution import verify
from ..sessions.summary import _record, utc
from .contracts import Contribution, Discovery, Week, day, monday
from .storage import ReportingStore


def build(session_store, reporting_store: ReportingStore, sequence, *, at=None):
    today = at or datetime.now(timezone.utc).date()
    first = monday(today) - timedelta(weeks=3)
    weeks = {first + timedelta(weeks=i): Week(start=(first + timedelta(weeks=i)).isoformat()).model_dump() for i in range(4)}
    active_days = {start: set() for start in weeks}
    passports = {start: set() for start in weeks}
    try:
        with session_store._connect() as db:
            for receipt, check in verify(db):
                finished = utc(receipt.finished_at).date()
                if not first <= finished <= today:
                    continue
                start = monday(finished)
                row, w = _record(receipt, check, timezone.utc), weeks[start]
                w["receipts"] += 1
                for target, source in (("during_changes", "during_count"), ("between_changes", "between_count"), ("reconstructable_changes", "reconstructable_changes")):
                    w[target] += row[source]
                w["meaningful_changes"] += row["during_count"] + row["between_count"]
                w["partial_receipts"] += int(row["partial"])
                w["incomplete_history_receipts"] += int(not row["change_count_complete"])
                active_days[start].add(finished)
                for field in ("passport_before", "passport_after"):
                    passport = row["receipt"].get(field)
                    if passport and passport["state"] == "consistent" and passport["model_reference"] == "consistent":
                        passports[start].add(passport["passport_id"])
    except FileNotFoundError:
        pass
    latest = None
    with reporting_store._connect() as db:
        profile = reporting_store._profile(db)
        if not profile["journal_complete"]:
            raise ContractError("reporting_journal_incomplete")
        rows = db.execute("SELECT day, kind, payload FROM operations ORDER BY rowid").fetchall()
        if len(rows) > 10_000:
            raise ContractError("reporting_journal_limit")
        for observed, kind, raw in rows:
            when = day(observed)
            if not first <= when <= today:
                continue
            start = monday(when)
            payload = load_json(raw)
            if kind == "scan":
                if set(payload) != {"successful", "discovery"} or type(payload["successful"]) is not bool:
                    raise ContractError("invalid_scan_count_record")
                candidate = Discovery.model_validate(payload["discovery"])
                if candidate.observed_on != observed or candidate.partial == payload["successful"]:
                    raise ContractError("invalid_scan_count_record")
                if latest is None or candidate.observed_on >= latest.observed_on:
                    latest = candidate
                weeks[start]["scans"] += 1
                weeks[start]["successful_scans"] += int(payload["successful"])
                active_days[start].add(when)
            elif kind == "passport" and payload == {}:
                weeks[start]["passport_versions_created"] += 1
            else:
                raise ContractError("invalid_operation_count_record")
    for start, week in weeks.items():
        week["active_days"] = len(active_days[start])
        week["active_passports"] = len(passports[start])
    return Contribution(sequence=sequence, generated_on=today.isoformat(),
                        weeks=tuple(Week(**w) for w in weeks.values()), latest_discovery=latest)

