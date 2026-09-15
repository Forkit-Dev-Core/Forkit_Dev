"""Private session records. These are not public export or signed binding schemas."""

from __future__ import annotations

import unicodedata
from pathlib import PurePosixPath
from typing import Annotated, Literal, TypeVar

from pydantic import AfterValidator, BeforeValidator, Field, model_validator

from ..contracts import UTC, Contract, Counter, Digest, Identifier, Token, _array

MAX_FILES = 2000
T = TypeVar("T")
Array = Annotated[tuple[T, ...], BeforeValidator(_array)]
Tool = Literal["claude-code", "codex", "cursor", "other"]
TOOL_NAMES = {
    "claude-code": "Claude Code",
    "codex": "Codex",
    "cursor": "Cursor",
    "other": "Selected tool",
}


def safe_relative(value: str) -> str:
    path = PurePosixPath(value)
    if (
        not value
        or len(value.encode("utf-8")) > 512
        or path.is_absolute()
        or any(p in {"", ".", ".."} for p in value.split("/"))
        or "\\" in value
        or len(path.parts) > 12
        or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)
    ):
        raise ValueError("unsafe_relative_path")
    return value


RelativePath = Annotated[str, AfterValidator(safe_relative)]


class FileState(Contract):
    path: RelativePath
    fingerprint: Digest
    executable: bool


class Snapshot(Contract):
    scope: Literal["session-source-files-v1"] = "session-source-files-v1"
    files: Annotated[Array[FileState], Field(max_length=MAX_FILES)]
    unknown_paths: Annotated[Array[RelativePath], Field(max_length=MAX_FILES * 2)]
    excluded_count: Counter
    inventory_complete: bool
    reasons: Annotated[Array[Token], Field(max_length=32)]

    @model_validator(mode="after")
    def unique_paths(self):
        paths = tuple(f.path for f in self.files)
        if len(paths) != len(set(paths)) or len(self.unknown_paths) != len(set(self.unknown_paths)):
            raise ValueError("duplicate_snapshot_path")
        if set(paths) & set(self.unknown_paths):
            raise ValueError("contradictory_snapshot_path")
        return self


class ClockStamp(Contract):
    kind: Literal["continuous", "unavailable"]
    milliseconds: Counter | None
    boot_token: Digest | None

    @model_validator(mode="after")
    def available_fields(self):
        if (self.kind == "continuous") != (
            self.milliseconds is not None and self.boot_token is not None
        ):
            raise ValueError("inconsistent_clock")
        if self.kind == "unavailable" and (
            self.milliseconds is not None or self.boot_token is not None
        ):
            raise ValueError("unavailable_clock_has_values")
        return self


class Started(Contract):
    schema_version: Literal["1.0"] = "1.0"
    session_id: Identifier
    project_id: Identifier
    tool: Tool
    tool_basis: Literal["user_selected", "hook_reported"] = "user_selected"
    capture_mode: Literal["manual", "wrapper", "official_hook"]
    started_at: UTC
    clock: ClockStamp


class FileChange(Contract):
    kind: Literal["added", "removed", "modified", "possible_rename"]
    path: RelativePath
    previous_path: RelativePath | None = None

    @model_validator(mode="after")
    def rename_pair(self):
        if (self.kind == "possible_rename") != (self.previous_path is not None):
            raise ValueError("invalid_rename_pair")
        return self


class Receipt(Contract):
    schema_version: Literal["1.0"] = "1.0"
    session_id: Identifier
    project_id: Identifier
    previous_session_id: Identifier | None
    tool: Tool
    tool_basis: Literal["user_selected", "hook_reported"] = "user_selected"
    capture_mode: Literal["manual", "wrapper", "official_hook"]
    started_at: UTC
    finished_at: UTC
    elapsed_ms: Counter | None
    duration_basis: Literal["continuous_clock", "unknown"]
    status: Literal["completed", "interrupted"]
    exit_code: Annotated[int, Field(ge=-255, le=255)] | None
    outcome: Literal[
        "manual_stop",
        "hook_end",
        "command_exited",
        "command_failed",
        "launch_failed",
        "interrupted",
        "recovered",
    ]
    attribution: Literal["changes_observed_during_session"] = "changes_observed_during_session"
    comparison: Literal["complete", "partial"]
    file_changes: Annotated[Array[FileChange], Field(max_length=MAX_FILES * 2)]
    unknown_count: Counter
    excluded_before: Counter
    excluded_after: Counter
    reasons: Annotated[Array[Token], Field(max_length=32)]
    passport_id: None = None
    dependency_comparison: Literal["not_available"] = "not_available"
    configuration_comparison: Literal["not_available"] = "not_available"

    @model_validator(mode="after")
    def consistent_summary(self):
        if (self.elapsed_ms is not None) != (self.duration_basis == "continuous_clock"):
            raise ValueError("inconsistent_elapsed_time")
        if self.comparison == "complete" and self.unknown_count:
            raise ValueError("unknown_paths_cannot_be_complete")
        if (self.status == "interrupted") != (
            self.outcome in {"interrupted", "recovered", "launch_failed"}
        ):
            raise ValueError("inconsistent_session_outcome")
        if self.outcome == "recovered" and (
            self.elapsed_ms is not None or self.comparison != "partial"
        ):
            raise ValueError("recovery_end_is_unknown")
        paths = [p for c in self.file_changes for p in (c.path, c.previous_path) if p is not None]
        if len(paths) != len(set(paths)):
            raise ValueError("duplicate_changed_path")
        return self


def elapsed(start: ClockStamp, end: ClockStamp) -> int | None:
    if (
        start.kind == end.kind == "continuous"
        and start.boot_token is not None
        and start.boot_token == end.boot_token
        and start.milliseconds is not None
        and end.milliseconds is not None
        and end.milliseconds >= start.milliseconds
    ):
        return end.milliseconds - start.milliseconds
    return None
