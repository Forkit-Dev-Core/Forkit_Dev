"""Core's unchanged identity algorithm behind a strict, read-only input boundary."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from pydantic import TypeAdapter, model_validator

from ..contracts import UTC, Contract, Digest, Text, Token
from ..discovery.safeio import read_metadata
from ..jsonio import MAX_SAFE_INTEGER, ContractError, _integer, _pairs


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


class CoreIdentity(Contract):
    name: Text
    version: Text
    creator: Text
    organization: Text | None


class PassportCheck(Contract):
    passport_id: Digest | None
    kind: Literal["agent", "model"] | None
    status: Literal["consistent", "invalid", "missing", "unavailable", "unsupported"]
    reason: Token
    checked_at: UTC
    identity: CoreIdentity | None = None
    model_id: Digest | None = None

    @model_validator(mode="after")
    def consistency_shape(self):
        if self.status == "consistent" and (
            self.passport_id is None
            or self.kind is None
            or self.identity is None
            or (self.kind == "agent" and self.model_id is None)
        ):
            raise ValueError("incomplete_core_check")
        if self.status != "consistent" and (self.identity is not None or self.model_id is not None):
            raise ValueError("failed_check_has_no_metadata")
        return self


def core_json(raw: bytes) -> dict:
    """Core allows finite float settings; Radar's integer-only JCS is unchanged.

    No raw Core document or hash of its arbitrary metadata is retained/exported.
    """
    if type(raw) is not bytes or len(raw) > 65_536:
        raise ContractError("invalid_core_document")

    def number(s):
        value = float(s)
        if not math.isfinite(value) or abs(value) > MAX_SAFE_INTEGER:
            raise ContractError("invalid_core_number")
        return value

    def constant(_):
        raise ContractError("invalid_core_number")

    try:
        data = json.loads(
            raw.decode("utf-8"),
            object_pairs_hook=_pairs,
            parse_int=_integer,
            parse_float=number,
            parse_constant=constant,
        )
        if type(data) is not dict:
            raise ValueError
        pending, nodes = [(data, 0)], 0
        while pending:
            item, depth = pending.pop()
            nodes += 1
            if nodes > 20_000 or depth > 32:
                raise ValueError
            if isinstance(item, dict):
                pending.extend((v, depth + 1) for pair in item.items() for v in pair)
            elif isinstance(item, list):
                pending.extend((v, depth + 1) for v in item)
            elif isinstance(item, str):
                item.encode("utf-8", errors="strict")
        return data
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("invalid_core_document") from None


def _passport(data: dict, *, creation=False):
    from forkit.domain.integrity import verify_passport_id
    from forkit.schemas import AgentPassport, ModelPassport

    kind = data.get("passport_type")
    if kind not in {"agent", "model"}:
        raise ContractError("unsupported_passport_type")
    creator = data.get("creator")
    if type(creator) is not dict or set(creator) - {"name", "organization", "email", "url"}:
        raise ContractError("invalid_creator")
    identity = CoreIdentity(
        name=data.get("name"),
        version=data.get("version"),
        creator=creator.get("name"),
        organization=creator.get("organization"),
    )
    if any(not v.strip() for v in (identity.name, identity.version, identity.creator)):
        raise ContractError("required_metadata_missing")
    # Core constructors coerce some fields; validate identity-bearing raw types first.
    for key in (
        "artifact_hash",
        "parent_hash",
        "parent_agent_id",
        "endpoint_hash",
        "base_model_id",
    ):
        if data.get(key) is not None:
            TypeAdapter(Digest).validate_python(data[key], strict=True)
    if kind == "agent":
        TypeAdapter(Digest).validate_python(data.get("model_id"), strict=True)
    if not creation:
        TypeAdapter(Digest).validate_python(data.get("id"), strict=True)
        if not verify_passport_id(data)["valid"]:
            raise ContractError("id_mismatch")
    elif "id" in data:
        raise ContractError("creation_cannot_supply_id")
    if kind == "agent":
        # Core's before-validators construct these nested models with default
        # extra-ignore settings. Check original nested JSON before that coercion.
        from forkit.schemas.pydantic._types import _SystemPromptRecordModel, _ToolRefModel

        if "tools" in data:
            if type(data["tools"]) is not list:
                raise ContractError("invalid_core_tools")
            for tool in data["tools"]:
                _ToolRefModel.model_validate_json(json.dumps(tool), strict=True, extra="forbid")
        if data.get("system_prompt") is not None:
            _SystemPromptRecordModel.model_validate_json(
                json.dumps(data["system_prompt"]), strict=True, extra="forbid"
            )
    cls = AgentPassport if kind == "agent" else ModelPassport
    # JSON-mode strict validation accepts Core enum strings without coercing numbers.
    passport = cls.model_validate_json(json.dumps(data), strict=True, extra="forbid")
    if passport.passport_type != kind or not verify_passport_id(passport.to_dict())["valid"]:
        raise ContractError("core_roundtrip_mismatch")
    if not creation and passport.id != data["id"]:
        raise ContractError("core_roundtrip_mismatch")
    return passport, identity


def check_bytes(raw: bytes, *, expected_id: str | None = None, expected_kind=None) -> PassportCheck:
    kind, identifier = None, None
    try:
        if expected_id is not None:
            TypeAdapter(Digest).validate_python(expected_id, strict=True)
        data = core_json(raw)
        passport, identity = _passport(data)
        kind, identifier = passport.passport_type, passport.id
        if (expected_id is not None and identifier != expected_id) or (
            expected_kind is not None and kind != expected_kind
        ):
            raise ContractError("record_identity_mismatch")
        return PassportCheck(
            passport_id=identifier,
            kind=kind,
            status="consistent",
            reason="raw_id_and_schema_checked",
            checked_at=now(),
            identity=identity,
            model_id=data["model_id"] if kind == "agent" else None,
        )
    except ImportError:
        return PassportCheck(
            passport_id=None,
            kind=None,
            status="unavailable",
            reason="core_dependency_unavailable",
            checked_at=now(),
        )
    except (ValueError, TypeError, KeyError):
        return PassportCheck(
            passport_id=None,
            kind=None,
            status="invalid",
            reason="raw_identity_or_schema_invalid",
            checked_at=now(),
        )


def check_file(path: Path, *, expected_id=None, expected_kind=None) -> PassportCheck:
    try:
        return check_bytes(
            read_metadata(path.absolute()), expected_id=expected_id, expected_kind=expected_kind
        )
    except FileNotFoundError:
        status, reason = "missing", "passport_not_found"
    except (OSError, ValueError):
        status, reason = "unavailable", "passport_unreadable"
    return PassportCheck(
        passport_id=None, kind=None, status=status, reason=reason, checked_at=now()
    )


def lookup(root: Path, passport_id: str, kind: Literal["agent", "model"]) -> PassportCheck:
    try:
        TypeAdapter(Digest).validate_python(passport_id, strict=True)
        if kind not in {"agent", "model"}:
            raise ValueError
    except ValueError:
        raise ContractError("invalid_passport_selection") from None
    # No LocalRegistry construction/indexing/repair; exact file and expected type only.
    return check_file(
        root.absolute() / f"{kind}s" / f"{passport_id}.json",
        expected_id=passport_id,
        expected_kind=kind,
    )


def create_bytes(raw: bytes, *, model_passport: bytes | None = None) -> bytes:
    data = core_json(raw)
    if type(data.get("creator")) is not dict:
        raise ContractError("required_core_metadata_invalid")
    if data.get("passport_type") == "agent":
        if (
            model_passport is None
            or check_bytes(
                model_passport, expected_id=data.get("model_id"), expected_kind="model"
            ).status
            != "consistent"
        ):
            raise ContractError("checked_model_passport_required")
    elif model_passport is not None:
        raise ContractError("unexpected_model_reference_document")
    # Creation accepts reviewed required metadata only. No prompts, arbitrary metadata,
    # artifact hash manufacture, auto model inference, or hidden registry changes.
    allowed = {
        "passport_type",
        "name",
        "version",
        "creator",
        "model_id",
        "task_type",
        "architecture",
    }
    if set(data) - allowed or set(data.get("creator", {})) - {"name", "organization"}:
        raise ContractError("unsupported_creation_fields")
    try:
        passport, _ = _passport(data, creation=True)
        encoded = (
            json.dumps(passport.to_dict(), indent=2, ensure_ascii=False).encode("utf-8") + b"\n"
        )
        if check_bytes(encoded).status != "consistent":
            raise ValueError
        return encoded
    except ImportError:
        raise ContractError("core_dependency_unavailable") from None
    except (ValueError, TypeError, KeyError):
        raise ContractError("required_core_metadata_invalid") from None
