"""Versioned private receipt details; the original 1.0 records stay immutable."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import Field, model_validator

from ..contracts import Contract, Counter, Digest, Identifier, Text, Token
from .models import Array, FileChange, Receipt, Snapshot

Category = Literal["dependencies", "configuration", "tools", "models"]
State = Literal["complete", "absent", "partial", "unavailable", "unsupported"]
Label = Annotated[Text, Field(max_length=256)]


class Selection(Contract):
    # Private locators, never included in receipt JSON. No implicit home scan.
    agent_manifest: str | None = None
    registry: str | None = None
    passport_id: Digest | None = None


class Fact(Contract):
    key: Label
    label: Label
    value: Label


class Source(Contract):
    key: Token
    category: Category
    state: State
    reason: Token
    facts: Annotated[Array[Fact], Field(max_length=512)] = ()

    @model_validator(mode="after")
    def unique(self):
        keys = [f.key for f in self.facts]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_metadata_key")
        if self.state in {"absent", "unavailable", "unsupported"} and self.facts:
            raise ValueError("unavailable_source_has_facts")
        return self


class Passport(Contract):
    state: Literal["not_selected", "consistent", "unavailable", "conflicted"]
    reason: Token
    basis: Literal["explicit_declared_association"] = "explicit_declared_association"
    passport_id: Digest | None = None
    name: Text | None = None
    version: Text | None = None
    model_id: Digest | None = None
    model_reference: Literal["not_checked", "consistent", "missing", "invalid", "unavailable"] = (
        "not_checked"
    )

    @model_validator(mode="after")
    def checked_identity(self):
        values = (self.passport_id, self.name, self.version, self.model_id)
        if self.state == "consistent" and any(v is None for v in values):
            raise ValueError("passport_identity_required")
        if self.state != "consistent" and any(v is not None for v in values):
            raise ValueError("unavailable_passport_has_identity")
        return self


class Metadata(Contract):
    profile: Literal["session-declared-metadata-v1"] = "session-declared-metadata-v1"
    sources: Annotated[Array[Source], Field(max_length=20)]
    passport: Passport

    @model_validator(mode="after")
    def unique(self):
        keys = [s.key for s in self.sources]
        if len(keys) != len(set(keys)):
            raise ValueError("duplicate_metadata_source")
        return self


class DetailedSnapshot(Contract):
    schema_version: Literal["2.0"] = "2.0"
    files: Snapshot
    selection: Selection
    metadata: Metadata


class Change(Contract):
    source: Token
    category: Category
    key: Label
    label: Label
    kind: Literal["added", "removed", "changed"]
    before: Label | None
    after: Label | None

    @model_validator(mode="after")
    def endpoints(self):
        if (
            (self.kind == "added" and (self.before is not None or self.after is None))
            or (self.kind == "removed" and (self.before is None or self.after is not None))
            or (
                self.kind == "changed"
                and (self.before is None or self.after is None or self.before == self.after)
            )
        ):
            raise ValueError("invalid_metadata_change")
        return self


class Coverage(Contract):
    source: Token
    category: Category
    before: State
    after: State
    comparison: Literal["complete", "partial"]
    before_reason: Token
    after_reason: Token


class Delta(Contract):
    basis: Literal["declared_metadata_endpoints"] = "declared_metadata_endpoints"
    changes: Annotated[Array[Change], Field(max_length=4096)]
    coverage: Annotated[Array[Coverage], Field(max_length=20)]
    passport_change: Literal["not_selected", "unchanged", "changed", "unknown"]

    @model_validator(mode="after")
    def consistent_changes(self):
        coverage = {c.source: c for c in self.coverage}
        if len(coverage) != len(self.coverage):
            raise ValueError("duplicate_comparison_source")
        identities = [(c.source, c.key) for c in self.changes]
        if len(identities) != len(set(identities)):
            raise ValueError("duplicate_metadata_change")
        for source in self.coverage:
            complete = source.before in {"complete", "absent"} and source.after in {
                "complete",
                "absent",
            }
            if (source.comparison == "complete") != complete:
                raise ValueError("inconsistent_source_coverage")
        for change in self.changes:
            source = coverage.get(change.source)
            if source is None or source.category != change.category:
                raise ValueError("uncovered_metadata_change")
            if change.kind != "changed" and source.comparison != "complete":
                raise ValueError("incomplete_source_cannot_add_or_remove")
        return self

    def status(self, category: str | None = None) -> str:
        return (
            "partial"
            if any(
                c.comparison == "partial"
                for c in self.coverage
                if category is None or c.category == category
            )
            else "complete"
        )


class Comparison(Contract):
    baseline_session_id: Identifier | None
    comparison: Literal["no_baseline", "complete", "partial"]
    reason: Token
    skipped_sessions: Counter
    file_changes: Annotated[Array[FileChange], Field(max_length=4000)] = ()
    unknown_count: Counter = 0
    metadata: Delta | None = None

    @model_validator(mode="after")
    def baseline(self):
        if self.comparison == "no_baseline":
            if (
                self.baseline_session_id is not None
                or self.file_changes
                or self.metadata is not None
            ):
                raise ValueError("missing_baseline_has_changes")
        elif self.baseline_session_id is None or self.metadata is None:
            raise ValueError("comparison_requires_baseline")
        elif self.comparison == "complete" and (
            self.unknown_count
            or self.metadata.status() != "complete"
            or self.metadata.passport_change == "unknown"
        ):
            raise ValueError("incomplete_previous_comparison")
        return self


class ReceiptV2(Receipt):
    schema_version: Literal["2.0"] = "2.0"
    passport_id: Digest | None = None
    dependency_comparison: Literal["complete", "partial"]
    configuration_comparison: Literal["complete", "partial"]
    metadata: Delta
    passport_before: Passport
    passport_after: Passport
    since_previous: Comparison
    between_sessions: Comparison
    runtime_observation: Literal["not_observed"] = "not_observed"
    meaningful_categories: Annotated[
        Array[Literal["files", "dependencies", "configuration", "tools", "models", "passport"]],
        Field(max_length=6),
    ]

    @model_validator(mode="after")
    def consistent_details(self):
        expected = categories(self.file_changes, self.metadata)
        if (
            self.meaningful_categories != expected
            or self.passport_id != self.passport_after.passport_id
        ):
            raise ValueError("inconsistent_receipt_details")
        if self.dependency_comparison != self.metadata.status("dependencies"):
            raise ValueError("inconsistent_dependency_coverage")
        config = (
            "partial"
            if any(
                c.comparison == "partial" and c.category != "dependencies"
                for c in self.metadata.coverage
            )
            else "complete"
        )
        if self.configuration_comparison != config:
            raise ValueError("inconsistent_configuration_coverage")
        return self


def categories(files, delta: Delta) -> tuple[str, ...]:
    found = {c.category for c in delta.changes}
    if files:
        found.add("files")
    if delta.passport_change == "changed":
        found.add("passport")
    return tuple(
        c
        for c in ("files", "dependencies", "configuration", "tools", "models", "passport")
        if c in found
    )


def difference(before: Metadata, after: Metadata) -> Delta:
    sources = {s.key: s for s in before.sources}, {s.key: s for s in after.sources}
    changes, coverage = [], []
    for key in sorted(sources[0].keys() | sources[1].keys()):
        a, b = sources[0].get(key), sources[1].get(key)
        category = (a or b).category
        a = a or Source(key=key, category=category, state="unavailable", reason="not_captured")
        b = b or Source(key=key, category=category, state="unavailable", reason="not_captured")
        complete = (
            a.category == b.category
            and a.state in {"complete", "absent"}
            and b.state in {"complete", "absent"}
        )
        coverage.append(
            Coverage(
                source=key,
                category=category,
                before=a.state,
                after=b.state,
                comparison="complete" if complete else "partial",
                before_reason=a.reason,
                after_reason=b.reason,
            )
        )
        old, new = {f.key: f for f in a.facts}, {f.key: f for f in b.facts}
        for fact_key in sorted(old.keys() | new.keys()):
            left, right = old.get(fact_key), new.get(fact_key)
            if left and right and left.value != right.value:
                kind = "changed"
            elif complete and (left is None or right is None):
                kind = "added" if left is None else "removed"
            else:
                continue
            changes.append(
                Change(
                    source=key,
                    category=category,
                    key=fact_key,
                    label=(right or left).label,
                    kind=kind,
                    before=left.value if left else None,
                    after=right.value if right else None,
                )
            )
    a, b = before.passport, after.passport
    if a.state == b.state == "not_selected":
        passport = "not_selected"
    elif (
        a.state == b.state == "consistent"
        and a.model_reference == b.model_reference == "consistent"
    ):
        passport = (
            "unchanged" if (a.passport_id, a.model_id) == (b.passport_id, b.model_id) else "changed"
        )
    else:
        passport = "unknown"
    return Delta(changes=changes, coverage=coverage, passport_change=passport)


def complete(metadata: Metadata) -> bool:
    return all(s.state in {"complete", "absent"} for s in metadata.sources) and (
        metadata.passport.state == "not_selected"
        or metadata.passport.state == "consistent"
        and metadata.passport.model_reference == "consistent"
    )
