"""Allowlisted counters from original local operations, never re-exports."""

import sys
from datetime import datetime, timezone
from uuid import uuid4

from ..sessions.evolution import verify
from ..sessions.summary import _record, utc
from .usage_contracts import ENGAGEMENT_POLICY
from .usage_storage import UsageStore, root

PRODUCTS = {
    "Codex": "codex",
    "Codex CLI": "codex",
    "Claude Code": "claude-code",
    "Cursor": "cursor",
}


def engagement(action):
    """Intentional local UI/CLI actions only; no view contents or IDs collected."""
    if action not in {'view', 'history', 'card'}:
        return
    store = UsageStore(root())
    try:
        status = store.status()
        if status['state'] != 'enabled' or status['consent'] != ENGAGEMENT_POLICY:
            return
        when = datetime.now(timezone.utc)
        identity = str(uuid4()) if action == 'card' else action + ':' + when.date().isoformat()
        store.event('engagement', identity, dict(viewed=int(action != 'card'),
            history_viewed=int(action == 'history'), card_exports=int(action == 'card')), observed=when)
        from .usage_worker import kick
        kick(store)
    except Exception:
        # Engagement never prevents a result or leaks private exception details.
        try:
            with store._connect(write=True) as db:
                p = store._profile(db)
                p['collection_complete'] = False
                store._save(db, p)
        except Exception:
            pass


def receipt(store, sessions, original, *, include_previous=False):
    with sessions._connect() as db:
        for candidate, check in verify(db):
            if candidate.session_id != original.session_id:
                continue
            row = _record(candidate, check, timezone.utc)
            passports = []
            for field in ("passport_before", "passport_after"):
                link = row["receipt"].get(field)
                if (
                    link
                    and link["state"] == "consistent"
                    and link["model_reference"] == "consistent"
                ):
                    passports.append(link["passport_id"])
            selected = (
                candidate.tool if candidate.tool in {"codex", "claude-code", "cursor"} else "other"
            )
            store.event(
                "receipt",
                candidate.session_id,
                dict(
                    receipts=1,
                    during_changes=row["during_count"],
                    between_changes=row["between_count"],
                    reconstructable_changes=row["reconstructable_changes"],
                    partial_receipts=int(row["partial"]),
                    incomplete_history_receipts=int(not row["change_count_complete"]),
                ),
                passports=passports,
                selected=selected,
                observed=utc(candidate.finished_at),
                include_previous=include_previous,
            )
            return


def scan(store, report):
    complete = bool(report.sources) and all(
        s.status in {"complete", "missing"} for s in report.sources
    )
    detected = set()
    observations = 0
    for source in report.sources:
        for finding in source.findings:
            manifest = finding.observation.manifest
            if manifest is None:
                continue
            observations += 1
            # Arbitrary agent manifests/config names cannot claim tool presence.
            if source.detector in {"applications", "processes"}:
                name = manifest.declared_identity.name.value
                detected.add(PRODUCTS.get(name, "other"))
    store.event(
        "scan",
        report.scan_id,
        dict(scans=1, successful_scans=int(complete), detection_observations=observations),
        detected=detected,
        observed=utc(report.finished_at),
    )


def safely_record(kind, *args):
    try:
        store = UsageStore(root())
        if store.status()["state"] != "enabled":
            return
        if kind == "receipt":
            receipt(store, *args)
        elif kind == "scan":
            scan(store, *args)
        elif kind == "passport":
            store.event("passport", args[0], dict(passport_versions_created=1))
        from .usage_worker import kick

        kick(store)
    except Exception:
        try:
            with store._connect(write=True) as db:
                p = store._profile(db)
                p["collection_complete"] = False
                store._save(db, p)
        except Exception:
            pass
        print(
            "Local result saved. Optional usage reporting unavailable; counts may be incomplete.",
            file=sys.stderr,
        )
