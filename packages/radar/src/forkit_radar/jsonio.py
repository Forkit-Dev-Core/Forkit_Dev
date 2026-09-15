"""Bounded JSON input for untrusted documents, with non-disclosing errors."""

from __future__ import annotations

import json
from typing import Any

MAX_DOCUMENT_BYTES = 1_048_576
MAX_DEPTH = 32
MAX_NODES = 20_000
MAX_STRING_LENGTH = 131_072
MAX_SAFE_INTEGER = 2**53 - 1


class ContractError(ValueError):
    """Only fixed error codes may cross the CLI/log boundary; never rejected input."""


def _pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ContractError("duplicate_key")
        result[key] = value
    return result


def _integer(value: str) -> int:
    if len(value.lstrip("-")) > 16:
        raise ContractError("integer_out_of_range")
    result = int(value)
    if abs(result) > MAX_SAFE_INTEGER:
        raise ContractError("integer_out_of_range")
    return result


def _no_float(_value: str) -> None:
    raise ContractError("non_integer_number")


def _no_constant(_value: str) -> None:
    raise ContractError("non_finite_number")


def load_json(raw: bytes, *, max_nodes: int = MAX_NODES) -> dict[str, Any]:
    """Accept a UTF-8 JSON object, without type coercion or input repair.

    The default node limit remains 20,000 for all public/metadata inputs. Private
    grouped session records explicitly use a bounded 100,000-node budget.
    Limits apply before schema validation, including unknown fields. Escaped
    Unicode must encode to UTF-8; duplicate names are rejected at every depth.
    Decimal settings use schema-defined strings, never floating-point JSON.
    """
    if type(raw) is not bytes:
        raise ContractError("bytes_required")
    if len(raw) > MAX_DOCUMENT_BYTES:
        raise ContractError("document_too_large")
    try:
        value = json.loads(
            raw.decode("utf-8", errors="strict"),
            object_pairs_hook=_pairs,
            parse_int=_integer,
            parse_float=_no_float,
            parse_constant=_no_constant,
        )
    except ContractError:
        raise
    except (ValueError, UnicodeError, RecursionError):
        raise ContractError("invalid_json") from None
    if type(value) is not dict:
        raise ContractError("object_required")
    stack = [(value, 0)]
    nodes = 0
    while stack:
        item, depth = stack.pop()
        nodes += 1
        if nodes > max_nodes:
            raise ContractError("too_many_nodes")
        if depth > MAX_DEPTH:
            raise ContractError("too_deep")
        if isinstance(item, str):
            if len(item) > MAX_STRING_LENGTH:
                raise ContractError("string_too_long")
            try:
                item.encode("utf-8", errors="strict")
            except UnicodeError:
                raise ContractError("invalid_unicode") from None
        elif type(item) is dict:
            for key, child in item.items():
                stack.extend(((key, depth + 1), (child, depth + 1)))
        elif type(item) is list:
            stack.extend((child, depth + 1) for child in item)
    return value
