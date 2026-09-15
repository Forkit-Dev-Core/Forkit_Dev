"""A separate aggregate-only wire contract. No private records are serialized."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Entries, Identifier
from ..jsonio import ContractError

Count = Annotated[int, Field(ge=0, le=100_000_000)]
Day = Annotated[str, Field(pattern=r"^[0-9]{4}-[0-9]{2}-[0-9]{2}$")]
POLICY = "session-metrics-v1"


def day(value):
    try:
        parsed = date.fromisoformat(value)
        if parsed.isoformat() != value:
            raise ValueError
        return parsed
    except (TypeError, ValueError):
        raise ContractError("invalid_reporting_date") from None


def monday(value):
    return value - timedelta(days=value.weekday())


class Week(Contract):
    start: Day
    active_days: Annotated[int, Field(ge=0, le=7)] = 0
    scans: Count = 0
    successful_scans: Count = 0
    receipts: Count = 0
    meaningful_changes: Count = 0
    during_changes: Count = 0
    between_changes: Count = 0
    reconstructable_changes: Count = 0
    incomplete_history_receipts: Count = 0
    partial_receipts: Count = 0
    active_passports: Count = 0
    passport_versions_created: Count = 0

    @model_validator(mode="after")
    def consistent(self):
        if (
            day(self.start).weekday() != 0
            or self.successful_scans > self.scans
            or self.active_days > self.scans + self.receipts
            or self.meaningful_changes != self.during_changes + self.between_changes
            or self.reconstructable_changes > self.during_changes
            or self.incomplete_history_receipts > self.receipts
            or self.partial_receipts > self.receipts
            or self.active_passports > self.receipts * 2
            or not self.receipts and self.meaningful_changes
        ):
            raise ValueError("inconsistent_reporting_week")
        return self


class Discovery(Contract):
    observed_on: Day
    models: Count | None
    agents: Count | None
    mcp_servers: Count | None
    applications_and_processes: Count | None
    partial: bool

    @model_validator(mode="after")
    def valid_day(self):
        day(self.observed_on)
        return self


class Contribution(Contract):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["forkit_usage_contribution"] = "forkit_usage_contribution"
    policy: Literal["session-metrics-v1"] = POLICY
    sequence: Annotated[int, Field(ge=1, le=1_000_000_000)]
    generated_on: Day
    weeks: Annotated[Entries[Week], Field(min_length=4, max_length=4)]
    latest_discovery: Discovery | None

    @model_validator(mode="after")
    def window(self):
        today = day(self.generated_on)
        first = monday(today) - timedelta(weeks=3)
        expected = [(first + timedelta(weeks=i)).isoformat() for i in range(4)]
        if [w.start for w in self.weeks] != expected:
            raise ValueError("invalid_reporting_window")
        if self.weeks[-1].active_days > today.weekday() + 1:
            raise ValueError("future_activity_days")
        if self.latest_discovery and not first <= day(self.latest_discovery.observed_on) <= today:
            raise ValueError("discovery_outside_reporting_window")
        return self


class Preview(Contract):
    schema_version: Literal["1.0"] = "1.0"
    kind: Literal["forkit_private_contribution_preview"] = "forkit_private_contribution_preview"
    endpoint: str
    surface_id: Identifier
    payload_sha256: Annotated[str, Field(pattern=r"^[a-f0-9]{64}$")]
    payload: Contribution
