"""
forkit.schemas.base
───────────────────
BasePassport — the dataclass base for ModelPassport and AgentPassport.

All validation, ID derivation, serialisation, and deserialisation logic lives
here.  Subclasses call super().__post_init__() after coercing their own fields.

Identity contract (never change without a version bump)
───────────────────────────────────────────────────────
  id = sha256(artifact_hash + "|" + canonical_json)  when artifact_hash present
  id = sha256(canonical_json)                         otherwise

  canonical_json = json.dumps(
      {passport_type, name, version, creator_name, creator_org},
      sort_keys=True, encoding="utf-8"
  )
"""

from __future__ import annotations

import dataclasses
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from ..domain.identity import compute_id, validate_hash, validate_version, to_json_safe
from .enums import LicenseType, PassportStatus
from .types import CreatorInfo


@dataclass(kw_only=True)
class BasePassport:
    """
    Pure-Python base passport.

    Fields prefixed with `_` in comments are computed automatically and should
    not be set by callers unless replaying a serialised passport.
    """

    # ── Required ──────────────────────────────────────────────────────────────
    name:    str
    version: str
    creator: CreatorInfo | dict

    # ── Provenance ────────────────────────────────────────────────────────────
    artifact_hash: str | None = None
    parent_hash:   str | None = None

    # ── Legal ─────────────────────────────────────────────────────────────────
    license:     LicenseType | str = LicenseType.OTHER
    license_url: str | None        = None

    # ── Identity (auto-computed; pass to replay a stored passport) ────────────
    id:          str            = field(default="")
    description: str | None     = None

    # ── Registry ──────────────────────────────────────────────────────────────
    status:   PassportStatus | str = PassportStatus.DRAFT
    tags:     list[str]            = field(default_factory=list)
    metadata: dict[str, Any]       = field(default_factory=dict)

    # ── Timestamps ────────────────────────────────────────────────────────────
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def __post_init__(self) -> None:
        # Coerce nested object
        if isinstance(self.creator, dict):
            self.creator = CreatorInfo.from_dict(self.creator)

        # Coerce enums from strings (enables JSON round-trips)
        if isinstance(self.license, str):
            self.license = LicenseType(self.license)
        if isinstance(self.status, str):
            self.status = PassportStatus(self.status)

        # Validate hash formats (normalises to lowercase)
        self.artifact_hash = validate_hash(self.artifact_hash)
        self.parent_hash   = validate_hash(self.parent_hash)

        # Validate version format
        self.version = validate_version(self.version)

        # Derive id if not already set (i.e. new passport, not a replay)
        # `metadata`, `status`, tags, and any future application-side attachments
        # are intentionally excluded from identity derivation.
        if not self.id:
            self.id = compute_id(
                passport_type = getattr(self, "passport_type", self.__class__.__name__),
                name          = self.name,
                version       = self.version,
                creator_name  = self.creator.name,
                creator_org   = self.creator.organization,
                artifact_hash = self.artifact_hash,
            )

    # ── Serialisation ─────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-safe dict (enums → .value, datetimes → .isoformat)."""
        raw = dataclasses.asdict(self)
        return json.loads(json.dumps(raw, default=to_json_safe))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "BasePassport":
        """
        Reconstruct a passport from a plain dict.

        - Drops `passport_type` (set by the subclass).
        - If `id` is absent it is re-derived from the identity fields.
        - Coercion of nested objects happens in __post_init__.
        """
        d = dict(d)
        d.pop("passport_type", None)
        if isinstance(d.get("creator"), dict):
            d["creator"] = CreatorInfo.from_dict(d["creator"])
        return cls(**d)

    # ── Helpers ────────────────────────────────────────────────────────────────

    def short_id(self, length: int = 12) -> str:
        return self.id[:length]

    def __repr__(self) -> str:
        return (
            f"<{self.__class__.__name__} "
            f"name={self.name!r} version={self.version!r} "
            f"id={self.short_id()}...>"
        )
