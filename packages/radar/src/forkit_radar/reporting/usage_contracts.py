"""Count-only usage protocol; independent of existing manual publication consent."""

from __future__ import annotations

from datetime import timedelta
from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Entries
from .contracts import Count, Day, day

POLICY = "usage-v2"
ENGAGEMENT_POLICY = "usage-v3"
ENGAGEMENT_COUNTERS = ("viewed", "history_viewed", "card_exports")
TOOLS = ("codex", "claude-code", "cursor", "other")
Tool = Literal["codex", "claude-code", "cursor", "other"]
COUNTERS = (
    "scans",
    "successful_scans",
    "detection_observations",
    "receipts",
    "during_changes",
    "between_changes",
    "reconstructable_changes",
    "partial_receipts",
    "incomplete_history_receipts",
    "passport_versions_created",
)


class ToolCounts(Contract):
    codex: Count = 0
    claude_code: Count = 0
    cursor: Count = 0
    other: Count = 0


class UsageDay(Contract):
    date: Day
    scans: Count = 0
    successful_scans: Count = 0
    detection_observations: Count = 0
    receipts: Count = 0
    during_changes: Count = 0
    between_changes: Count = 0
    reconstructable_changes: Count = 0
    partial_receipts: Count = 0
    incomplete_history_receipts: Count = 0
    passport_versions_created: Count = 0
    detected_tools: Annotated[Entries[Tool], Field(max_length=4)] = ()
    session_tools: ToolCounts = ToolCounts()

    @model_validator(mode="after")
    def consistent(self):
        day(self.date)
        if (
            self.successful_scans > self.scans
            or self.reconstructable_changes > self.during_changes
            or self.partial_receipts > self.receipts
            or self.incomplete_history_receipts > self.receipts
            or (not self.receipts and self.during_changes + self.between_changes)
            or (not self.scans and (self.detection_observations or self.detected_tools))
            or sum(self.session_tools.model_dump().values()) != self.receipts
            or tuple(sorted(set(self.detected_tools))) != self.detected_tools
        ):
            raise ValueError("inconsistent_usage_day")
        return self


class PassportWindow(Contract):
    end_exclusive: Day
    distinct_passports: Count


class UsageContribution(Contract):
    schema_version: Literal["2.0"] = "2.0"
    kind: Literal["forkit_usage_contribution"] = "forkit_usage_contribution"
    policy: Literal["usage-v2"] = POLICY
    audience: Literal["community", "validation"]
    sequence: Annotated[int, Field(ge=1, le=1_000_000_000)]
    generated_on: Day
    collection_complete: bool
    days: Annotated[Entries[UsageDay], Field(min_length=29, max_length=29)]
    passport_windows: Annotated[Entries[PassportWindow], Field(min_length=29, max_length=29)]

    @model_validator(mode="after")
    def windows(self):
        end = day(self.generated_on)
        dates = [(end - timedelta(days=28 - i)).isoformat() for i in range(29)]
        if [d.date for d in self.days] != dates:
            raise ValueError("invalid_usage_dates")
        # Each window contains the seven complete UTC dates before its end.
        if [p.end_exclusive for p in self.passport_windows] != dates:
            raise ValueError("invalid_passport_windows")
        return self


class EngagementDay(UsageDay):
    viewed: Annotated[int, Field(strict=True, ge=0, le=1)] = 0
    history_viewed: Annotated[int, Field(strict=True, ge=0, le=1)] = 0
    card_exports: Count = 0

    @model_validator(mode="after")
    def viewing(self):
        if self.history_viewed > self.viewed:
            raise ValueError("history_requires_view")
        return self


class EngagementContribution(UsageContribution):
    schema_version: Literal["3.0"] = "3.0"
    policy: Literal["usage-v3"] = ENGAGEMENT_POLICY
    days: Annotated[Entries[EngagementDay], Field(min_length=29, max_length=29)]


def read_usage(value):
    if not isinstance(value, dict):
        raise ValueError("invalid_usage_contribution")
    cls = EngagementContribution if value.get("schema_version") == "3.0" else UsageContribution
    return cls.model_validate(value)
