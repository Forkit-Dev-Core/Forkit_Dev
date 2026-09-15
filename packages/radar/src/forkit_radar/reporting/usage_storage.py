"""Installation-scoped consent and bounded local counters, never a user identity."""

from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import UUID, uuid4

from rfc8785 import dumps

from ..identity.storage import EnrollmentStore
from ..jsonio import ContractError, load_json
from .client import checked_endpoint
from .contracts import day
from .usage_contracts import (
    COUNTERS,
    ENGAGEMENT_COUNTERS,
    ENGAGEMENT_POLICY,
    POLICY,
    TOOLS,
    EngagementContribution,
    EngagementDay,
    PassportWindow,
    UsageContribution,
    UsageDay,
    read_usage,
)


def root():
    # Explicit local override supports isolated installations/tests. Never sent.
    return Path(os.environ.get("FORKIT_USAGE_STORE", Path.home() / ".forkit-radar"))


def today():
    return datetime.now(timezone.utc).date()


def profile(value):
    keys = {
        "state",
        "endpoint",
        "allow_local",
        "surface_id",
        "credential",
        "sequence",
        "last_sent_sequence",
        "consent",
        "consented_at",
        "audience",
        "last_attempt",
        "pending",
        "attempts",
        "collection_complete",
        "last_result",
    }
    if type(value) is not dict or set(value) != keys:
        raise ContractError("invalid_usage_profile")
    p = value
    try:
        if (
            p["state"] not in {"enabled", "disabled", "withdrawn", "withdrawing"}
            or p["consent"] not in {POLICY, ENGAGEMENT_POLICY}
        ):
            raise ValueError
        if type(p["allow_local"]) is not bool or type(p["collection_complete"]) is not bool:
            raise ValueError
        checked_endpoint(p["endpoint"], allow_local=p["allow_local"])
        if str(UUID(p["surface_id"], version=4)) != p["surface_id"] or not re.fullmatch(
            r"[a-f0-9]{64}", p["credential"]
        ):
            raise ValueError
        if p["audience"] not in {"community", "validation"} or (
            p["allow_local"] and p["audience"] != "validation"
        ):
            raise ValueError
        for k in ("sequence", "last_sent_sequence", "last_attempt", "consented_at", "attempts"):
            if type(p[k]) is not int or not 0 <= p[k] <= 10_000_000_000:
                raise ValueError
        if (
            p["last_sent_sequence"] > p["sequence"]
            or p["sequence"] > 1_000_000_000
            or p["attempts"] > 3
        ):
            raise ValueError
        if p["last_result"] not in {
            "never_sent",
            "pending",
            "confirmed",
            "unconfirmed",
            "disabled",
            "withdrawn",
            "withdrawal_pending",
        }:
            raise ValueError
        if p["pending"] is not None:
            packet = read_usage(p["pending"])
            if packet.sequence != p["sequence"] or packet.audience != p["audience"] or packet.policy != p["consent"]:
                raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise ContractError("invalid_usage_profile") from None
    return p


class UsageStore(EnrollmentStore):
    database_name = "usage.sqlite3"
    application_id = 0x46525532
    schema_version = 1
    schema = (
        "CREATE TABLE settings (name TEXT PRIMARY KEY, value BLOB NOT NULL)",
        "CREATE TABLE profile (id INTEGER PRIMARY KEY CHECK(id=1), payload BLOB NOT NULL)",
        "CREATE TABLE events (event_key TEXT PRIMARY KEY, day TEXT NOT NULL, payload BLOB NOT NULL)",
        "CREATE TABLE seen_passports (passport_key TEXT PRIMARY KEY)",
    )

    @staticmethod
    def _profile(db):
        row = db.execute("SELECT payload FROM profile WHERE id=1").fetchone()
        if row is None:
            raise ContractError("usage_profile_missing")
        return profile(load_json(row[0]))

    @staticmethod
    def _save(db, p):
        profile(p)
        db.execute("UPDATE profile SET payload=? WHERE id=1", (dumps(p),))

    @staticmethod
    def _key(db, domain, value):
        key = db.execute("SELECT value FROM settings WHERE name='locator_key'").fetchone()[0]
        return hmac.new(key, (domain + "\n" + value).encode(), hashlib.sha256).hexdigest()

    def status(self):
        try:
            with self._connect() as db:
                p = self._profile(db)
                return {
                    k: p[k]
                    for k in (
                        "state",
                        "endpoint",
                        "audience",
                        "consent",
                        "last_result",
                        "last_sent_sequence",
                        "collection_complete",
                    )
                }
        except FileNotFoundError:
            return {
                "state": "disabled",
                "endpoint": None,
                "audience": None,
                "consent": None,
                "last_result": "never_sent",
                "last_sent_sequence": 0,
                "collection_complete": True,
            }

    def enable(self, endpoint, *, consent, validation=False, allow_local=False, now=None):
        if consent not in {POLICY, ENGAGEMENT_POLICY} or (allow_local and not validation):
            raise ContractError("explicit_usage_v2_consent_required")
        if os.environ.get("CI") and not validation:
            raise ContractError("ci_is_not_community_adoption")
        endpoint = checked_endpoint(endpoint, allow_local=allow_local)
        with self._connect(write=True, create=True) as db:
            row = db.execute("SELECT payload FROM profile WHERE id=1").fetchone()
            if row:
                p = self._profile(db)
                if p["state"] != "withdrawn":
                    if p['consent'] != consent:
                        raise ContractError('withdraw_before_changing_usage_policy')
                    if (p["endpoint"], p["allow_local"], p["audience"]) != (
                        endpoint,
                        allow_local,
                        "validation" if validation else "community",
                    ):
                        raise ContractError("withdraw_before_changing_usage_collector")
                    if p["state"] == "withdrawing":
                        raise ContractError("finish_withdrawal_first")
                    if p["state"] == "enabled":
                        return
                    p.update(
                        state="enabled",
                        consented_at=int(now if now is not None else time.time()),
                        pending=None,
                    )
                    self._save(db, p)
                    return
            p = dict(
                state="enabled",
                endpoint=endpoint,
                allow_local=allow_local,
                surface_id=str(uuid4()),
                credential=secrets.token_hex(32),
                sequence=0,
                last_sent_sequence=0,
                consent=consent,
                consented_at=int(now if now is not None else time.time()),
                audience="validation" if validation else "community",
                last_attempt=0,
                pending=None,
                attempts=0,
                collection_complete=True,
                last_result="never_sent",
            )
            db.execute(
                "INSERT INTO profile VALUES(1, ?) ON CONFLICT(id) DO UPDATE SET payload=excluded.payload",
                (dumps(profile(p)),),
            )
            db.execute("DELETE FROM events")
            db.execute("DELETE FROM seen_passports")

    def disable(self):
        if self.status()["consent"] is None:
            return
        with self._connect(write=True) as db:
            p = self._profile(db)
            if p["state"] not in {"withdrawn", "withdrawing"}:
                p.update(state="disabled", pending=None, last_result="disabled")
                self._save(db, p)

    def event(
        self,
        kind,
        identity,
        counters,
        *,
        passports=(),
        detected=(),
        selected=None,
        observed=None,
        include_previous=False,
    ):
        if self.status()["state"] != "enabled":
            return
        when = observed or datetime.now(timezone.utc)
        with self._connect(write=True) as db:
            p = self._profile(db)
            if p["state"] != "enabled" or (os.environ.get("CI") and p["audience"] != "validation"):
                return
            if not include_previous and when.timestamp() < p["consented_at"]:
                return
            event_key = self._key(db, kind, identity)
            if db.execute("SELECT 1 FROM events WHERE event_key=?", (event_key,)).fetchone():
                return
            if kind == "passport":
                if db.execute(
                    "SELECT 1 FROM seen_passports WHERE passport_key=?", (event_key,)
                ).fetchone():
                    return
                if db.execute("SELECT COUNT(*) FROM seen_passports").fetchone()[0] >= 100_000:
                    p["collection_complete"] = False
                    self._save(db, p)
                    return
            cutoff = (today() - timedelta(days=35)).isoformat()
            db.execute("DELETE FROM events WHERE day < ?", (cutoff,))
            if when.date().isoformat() < cutoff or when.date() > today():
                raise ContractError("event_outside_local_window")
            if db.execute("SELECT COUNT(*) FROM events").fetchone()[0] >= 10_000:
                p["collection_complete"] = False
                self._save(db, p)
                return
            engaged = p['consent'] == ENGAGEMENT_POLICY
            if kind == 'engagement' and not engaged:
                return
            day_type = EngagementDay if engaged else UsageDay
            values = {k: 0 for k in COUNTERS + (ENGAGEMENT_COUNTERS if engaged else ())}
            values.update(counters)
            sessions = {k.replace("-", "_"): int(k == selected) for k in TOOLS}
            record = day_type(
                date=when.date().isoformat(),
                **values,
                detected_tools=tuple(sorted(set(detected))),
                session_tools=sessions,
            )
            keys = sorted({self._key(db, "passport", key) for key in passports})
            payload = dict(counts=record.model_dump(mode="json"), passports=keys)
            db.execute(
                "INSERT OR IGNORE INTO events VALUES(?,?,?)",
                (event_key, record.date, dumps(payload)),
            )
            if kind == "passport":
                db.execute("INSERT INTO seen_passports VALUES(?)", (event_key,))

    def contribution(self, db, sequence, *, at=None):
        p = self._profile(db)
        engaged = p['consent'] == ENGAGEMENT_POLICY
        day_type = EngagementDay if engaged else UsageDay
        counters = COUNTERS + (ENGAGEMENT_COUNTERS if engaged else ())
        end = at or today()
        dates = [(end - timedelta(days=28 - i)).isoformat() for i in range(29)]
        rows = {d: day_type(date=d).model_dump(mode="json") for d in dates}
        passports = {}
        events = db.execute("SELECT day,payload FROM events ORDER BY day").fetchall()
        if len(events) > 10_000:
            raise ContractError("usage_journal_limit")
        for observed, raw in events:
            value = load_json(raw)
            if (
                set(value) != {"counts", "passports"}
                or type(value["passports"]) is not list
                or len(value["passports"]) > 2
                or any(
                    type(k) is not str or not re.fullmatch(r"[a-f0-9]{64}", k)
                    for k in value["passports"]
                )
            ):
                raise ContractError("invalid_usage_event")
            event = day_type.model_validate(value["counts"])
            if observed != event.date:
                raise ContractError("invalid_usage_event_date")
            passports.setdefault(observed, set()).update(value["passports"])
            if observed not in rows:
                continue
            target = rows[observed]
            for k in counters:
                target[k] += getattr(event, k)
                if k in {'viewed', 'history_viewed'}:
                    target[k] = min(1, target[k])
            target["detected_tools"] = sorted(
                set(target["detected_tools"]) | set(event.detected_tools)
            )
            for k, n in event.session_tools.model_dump().items():
                target["session_tools"][k] += n
        windows = []
        for d in dates:
            first = (day(d) - timedelta(days=7)).isoformat()
            members = set().union(*(v for k, v in passports.items() if first <= k < d))
            windows.append(PassportWindow(end_exclusive=d, distinct_passports=len(members)))
        return (EngagementContribution if engaged else UsageContribution)(
            audience=p["audience"],
            sequence=sequence,
            generated_on=end.isoformat(),
            collection_complete=p["collection_complete"],
            days=tuple(day_type(**r) for r in rows.values()),
            passport_windows=tuple(windows),
        )

    def preview(self, *, at=None):
        with self._connect() as db:
            p = self._profile(db)
            if p["state"] != "enabled":
                raise ContractError("usage_disabled")
            return self.contribution(db, p["sequence"] + 1, at=at)
