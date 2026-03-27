"""
forkit.domain.identity
──────────────────────
Core identity functions for passport ID derivation and field validation.

These are pure functions — no class state, no I/O, no external dependencies.
They are the single source of truth for how passport IDs are computed, so that
the dataclass backend, the optional Pydantic backend, and any future backends
all produce identical results.

Invariants (never change without a version bump)
────────────────────────────────────────────────
1. canonical JSON uses sort_keys=True, UTF-8 encoding.
2. When artifact_hash is present: payload = artifact_hash + "|" + canonical.
   When absent:                   payload = canonical.
3. Passport ID = sha256(payload).hexdigest()
4. Hash fields are normalised to lowercase before storage and validation.
5. Version must be 2- or 3-part semver (e.g. "1.0" or "1.0.0").
6. Application-side metadata such as sync state, labels, review notes, and
   runtime configuration never participates in the ID.
"""

from __future__ import annotations

import hashlib
import json
from enum import Enum
from typing import Any

__all__ = [
    "HASH_LENGTH",
    "compute_id",
    "validate_hash",
    "validate_version",
    "to_json_safe",
]

# ── Constants ─────────────────────────────────────────────────────────────────

_SHA_CHARS: frozenset[str] = frozenset("0123456789abcdef")
HASH_LENGTH: int = 64  # SHA-256 hex digest length


# ── Validation ────────────────────────────────────────────────────────────────

def validate_hash(value: str | None) -> str | None:
    """
    Normalise and validate a SHA-256 hex digest.

    Accepts uppercase hex and normalises it to lowercase.
    Returns None unchanged.
    Raises ValueError if the string is not valid 64-char hex.
    """
    if value is None:
        return None
    v = str(value).lower().strip()
    if len(v) != HASH_LENGTH or not all(c in _SHA_CHARS for c in v):
        raise ValueError(
            f"Hash must be a 64-char hex SHA-256 digest. Got: {value!r}"
        )
    return v


def validate_version(value: str) -> str:
    """
    Validate that a version string looks like semver (2 or 3 parts).

    Raises ValueError if the format does not match.
    """
    parts = str(value).split(".")
    if not (2 <= len(parts) <= 3):
        raise ValueError(
            f"Version must be 2- or 3-part semver (e.g. '1.0' or '1.0.0'). Got: {value!r}"
        )
    return value


# ── ID computation ─────────────────────────────────────────────────────────────

def compute_id(
    passport_type: str,
    name: str,
    version: str,
    creator_name: str,
    creator_org: str | None,
    artifact_hash: str | None = None,
) -> str:
    """
    Derive a deterministic SHA-256 passport ID from its identity fields.

    The identity fields are: passport_type, name, version, creator name and org.
    When artifact_hash is provided it is prepended to the payload so that two
    passports with the same metadata but different artifacts get different IDs.
    Additional application metadata must be attached separately and not written
    into the identity material.

    This function is the canonical implementation.  Both the dataclass and the
    optional Pydantic backends delegate here.
    """
    canonical = json.dumps(
        {
            "passport_type": passport_type,
            "name":          name,
            "version":       version,
            "creator_name":  creator_name,
            "creator_org":   creator_org,
        },
        sort_keys=True,
    )
    payload = (artifact_hash + "|" + canonical) if artifact_hash else canonical
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ── Serialisation helper ───────────────────────────────────────────────────────

def to_json_safe(obj: Any) -> Any:
    """
    JSON default encoder for objects not natively serialisable.

    Converts:
      - Enum          → .value  (string or int)
      - datetime/date → .isoformat()
      - anything else → str()
    """
    if isinstance(obj, Enum):
        return obj.value
    if hasattr(obj, "isoformat"):
        return obj.isoformat()
    return str(obj)
