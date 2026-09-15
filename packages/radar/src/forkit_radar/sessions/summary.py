"""Local calendar summaries from every retained receipt, with bounded display.

No source, project, registry, home inventory or network is reread. All periods
use receipt completion time; changes between captures have no known edit time.
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from pydantic import TypeAdapter

from ..contracts import Identifier
from ..jsonio import ContractError
from .details import ReceiptV2
from .evolution import verify
from .meaningful import CATEGORIES, POLICY, changes, counts


def zone(name=None):
    if name is not None:
        if not isinstance(name, str) or len(name) > 80:
            raise ContractError("invalid_timezone")
        try:
            return ZoneInfo(name), name
        except (KeyError, ValueError):
            raise ContractError("timezone_unavailable") from None
    # Preserve historical DST rules instead of using today's fixed UTC offset.
    try:
        with open("/etc/localtime", "rb") as handle:
            return ZoneInfo.from_file(handle), "System local timezone"
    except (OSError, ValueError):
        return timezone.utc, "UTC (local timezone unavailable)"


def utc(value):
    return datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def period(today, *, week=False):
    first = today - timedelta(days=today.weekday()) if week else today
    return {
        "start_date": first.isoformat(),
        "end_date_exclusive": (first + timedelta(days=7 if week else 1)).isoformat(),
        "receipts": 0, "file_changes": 0, "meaningful_changes": 0,
        "during_session_changes": 0, "between_session_changes": 0,
        "reconstructable_changes": 0, "reconstructable_change_rate": None,
        "reconstructable_change_rate_unit": "basis_points",
        "partial_receipts": 0, "unavailable_traces": 0,
        "incomplete_history_receipts": 0,
        "categories": dict.fromkeys(CATEGORIES, 0), "tools": {},
    }


def add(stats, record):
    receipt = record["receipt"]
    stats["receipts"] += 1
    stats["file_changes"] += len(receipt["file_changes"])
    stats["during_session_changes"] += record["during_count"]
    stats["between_session_changes"] += record["between_count"]
    stats["meaningful_changes"] += record["during_count"] + record["between_count"]
    stats["reconstructable_changes"] += record["reconstructable_changes"]
    stats["partial_receipts"] += int(record["partial"])
    stats["unavailable_traces"] += int(record["trace"] != "complete")
    stats["incomplete_history_receipts"] += int(not record["change_count_complete"])
    for category, count in record["category_counts"].items():
        stats["categories"][category] += count
    tool = receipt["tool"]
    stats["tools"][tool] = stats["tools"].get(tool, 0) + 1


def finish(stats):
    denominator = stats["meaningful_changes"]
    if denominator and not stats["incomplete_history_receipts"]:
        # Integer basis points preserve deterministic JSON without float inputs.
        stats["reconstructable_change_rate"] = stats["reconstructable_changes"] * 10_000 // denominator
    return stats


def _record(receipt, check, tz):
    details = isinstance(receipt, ReceiptV2)
    before, after = check["before"], check["after"]
    events = changes(
        receipt.file_changes, receipt.metadata if details else None,
        receipt.passport_before if details else None, receipt.passport_after if details else None,
    )
    gap, gap_status = [], "no_adjacent_comparable_evolution"
    if details and receipt.previous_session_id and receipt.between_sessions.baseline_session_id == receipt.previous_session_id:
        prior = receipt.between_sessions
        gap = changes(prior.file_changes, prior.metadata)
        gap_status = "saved_adjacent_comparison_evidence_unavailable"
    if before and after:
        file_changes, delta, _unknown, _complete = check["interval"]
        events = changes(file_changes, delta, before.metadata.passport, after.metadata.passport)
        if check["gap_before"]:
            gap_before = check["gap_before"]
            files, metadata, unknown, complete = check["gap_interval"]
            gap = changes(files, metadata, gap_before.metadata.passport, before.metadata.passport)
            gap_status = "complete" if complete and not unknown and metadata.status() == "complete" else "partial"
    trace = "complete"
    if check["status"] != "consistent":
        trace = check["reason"]
    elif receipt.outcome == "recovered":
        trace = "session_end_unknown"
    elif not details or any(
        p.state != "consistent" or p.model_reference != "consistent"
        for p in (receipt.passport_before, receipt.passport_after)
    ):
        trace = "consistent_selected_passport_required_at_both_endpoints"
    event = check["event"]
    category_counts = counts(events + gap)
    during_count, between_count = len(events), len(gap)
    if event:
        during_counts = event.during_counts.model_dump()
        between_counts = event.between_counts.model_dump() if event.between_counts else dict.fromkeys(CATEGORIES, 0)
        category_counts = {k: during_counts[k] + between_counts[k] for k in CATEGORIES}
        during_count, between_count = sum(during_counts.values()), sum(between_counts.values())
    count_complete = check["status"] == "consistent" or event is not None
    partial = receipt.comparison == "partial" or not details or details and (
        receipt.metadata.status() == "partial" or receipt.metadata.passport_change == "unknown"
    )
    return {
        "receipt": receipt.model_dump(mode="json"),
        "local_date": utc(receipt.finished_at).astimezone(tz).date().isoformat(),
        "local_finished_at": utc(receipt.finished_at).astimezone(tz).isoformat(),
        "partial": bool(partial), "trace": trace,
        "reconstructable_changes": during_count if trace == "complete" else 0,
        "during_count": during_count, "between_count": between_count,
        "category_counts": category_counts, "change_count_complete": count_complete,
        "changes": events, "between_changes": gap, "between_comparison": gap_status,
        "evolution": {
            "status": check["status"], "reason": check["reason"],
            "before_revision": event.before_revision if event else None,
            "after_revision": event.after_revision if event else None,
            "previous_session_id": event.previous_session_id if event else None,
            "previous_after_revision": event.previous_after_revision if event else None,
            "event_sequence": event.sequence if event else None,
            "basis": "unsigned_local_project_history_declared_passport_associations",
            "earlier_history_gap": bool(event and event.previous_project_session_id != event.previous_session_id),
        },
    }


def build(store, *, timezone_name=None, at=None, limit=200, project_id=None):
    if type(limit) is not int or not 1 <= limit <= 1000:
        raise ContractError("invalid_view_limit")
    if project_id is not None:
        TypeAdapter(Identifier).validate_python(project_id, strict=True)
    tz, tz_label = zone(timezone_name)
    current = at or datetime.now(timezone.utc)
    if not isinstance(current, datetime) or current.tzinfo is None:
        raise ContractError("aware_report_time_required")
    today = current.astimezone(tz).date()
    periods = {"today": period(today), "week": period(today, week=True), "history": period(today)}
    periods["history"].update(start_date=None, end_date_exclusive=None)
    displayed = deque(maxlen=limit)
    total, future, project_ids = 0, 0, set()
    active = []
    try:
        with store.history_connection() as db:
            for receipt, check in verify(db):
                if project_id and receipt.project_id != project_id:
                    continue
                total += 1
                project_ids.add(receipt.project_id)
                record = _record(receipt, check, tz)
                displayed.append(record)
                add(periods["history"], record)
                if utc(receipt.finished_at) > current:
                    future += 1
                    continue
                for name in ("today", "week"):
                    p = periods[name]
                    if p["start_date"] <= record["local_date"] < p["end_date_exclusive"]:
                        add(p, record)
            for row in db.execute("SELECT session_id, project_id, state, started FROM sessions WHERE state='active' ORDER BY rowid DESC LIMIT 101"):
                entry = store._entry(row)
                if project_id is None or entry.started.project_id == project_id:
                    active.append({"session_id": entry.started.session_id, "tool": entry.started.tool, "started_at": entry.started.started_at})
            if len(active) > 100:
                raise ContractError("session_listing_limit")
    except FileNotFoundError:
        pass
    return {
        "schema_version": "1.0", "kind": "forkit_private_evolution_view",
        "privacy": "private_local_only", "counting_policy": POLICY,
        "generated_at": current.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timezone": tz_label, "project_id": project_id,
        "total_receipts": total, "displayed_receipts": len(displayed),
        "display_limit": limit, "project_count": len(project_ids),
        "future_dated_receipts": future,
        "periods": {name: finish(p) for name, p in periods.items()},
        "records": list(reversed(displayed)), "active_sessions": active,
        "methodology": {
            "periods": "Calendar day and Monday-start calendar week in the selected timezone, grouped by receipt completion. Future-dated receipts are excluded from day/week totals.",
            "meaningful_changes": "One supported dependency package or configured component change per interval; explained metadata files count through their metadata, not twice. Other file changes count once. Separate sessions, projects and between-session intervals remain separate events.",
            "reconstruction": "Known change events with retained checked before/after state, an intact local event chain, a bounded session and a consistent explicitly selected agent/model Passport at both endpoints. The denominator includes all recorded meaningful events, including between-session events with unknown session attribution. Original event counts survive missing revision data. If event counts themselves cannot be established, the percentage is unavailable. Unknown/unobserved edits cannot be counted; partial coverage is shown separately. JSON rates use integer basis points: 10000 means 100 percent.",
            "identity": "Project history and declared Passport associations. Observed revisions do not create Core Passport versions, authenticate an enrolled agent, or prove authorship. Local records and heads are unsigned; a compromised account or rollback of the whole store is not resisted.",
            "retention": "New revision evidence survives snapshot compaction. Legacy receipt bytes are unchanged; missing old evidence is not manufactured. Calendar totals use all retained receipts; the timeline shows the most recent selected number.",
        },
    }


def text(report, which="week"):
    p = report["periods"][which]
    lines = ["FORKIT LOCAL SUMMARY", f"{'Today' if which == 'today' else 'This week' if which == 'week' else 'All retained history'} · {report['timezone']}", f"{p['receipts']} receipts · {p['meaningful_changes']} meaningful change events", f"{p['during_session_changes']} during sessions · {p['between_session_changes']} between captures"]
    for category, count in p["categories"].items():
        if count:
            lines.append(f"  {category}: {count}")
    denominator = p["meaningful_changes"]
    lines.append(f"Reconstructable: {p['reconstructable_changes']}/{denominator} recorded changes" if denominator else "Reconstructable: no recorded changes yet")
    if p["incomplete_history_receipts"]:
        lines.append(f"{p['incomplete_history_receipts']} receipts lack complete retained change-count evidence; reconstruction percentage unavailable.")
    lines.extend((f"{p['partial_receipts']} receipts with partial coverage · {p['unavailable_traces']} without a complete Passport/session trace", "Selected/configured tools and models; runtime use is unknown.", "Local only · no account or upload. Use view --output private.html for details."))
    return "\n".join(lines)
