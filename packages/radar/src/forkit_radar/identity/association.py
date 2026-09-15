"""Explicit references create candidates, never local authority or continuity."""

from pathlib import Path
from typing import Literal

from ..contracts import Contract, Digest, Entries, Manifest, Token
from .passports import PassportCheck, lookup


class Association(Contract):
    state: Literal["unmatched", "declared", "ambiguous", "conflicted"]
    reason: Token
    candidates: Entries[PassportCheck]
    selected_passport_id: Digest | None
    model_reference: Literal["not_checked", "consistent", "missing", "invalid", "unavailable"]


def resolve(manifest: Manifest, registry: Path | None = None, *, selected_ids=()) -> Association:
    # A declared ID and a different explicit selection are a conflict to resolve,
    # never permission to override one reference silently.
    ids = tuple(
        dict.fromkeys(
            ((manifest.passport_id,) if manifest.passport_id else ()) + tuple(selected_ids)
        )
    )
    if len(ids) > 16:
        raise ValueError("too_many_passport_candidates")
    if manifest.component_kind not in {"agent", "model"}:
        return Association(
            state="unmatched",
            reason="ineligible_component",
            candidates=(),
            selected_passport_id=None,
            model_reference="not_checked",
        )
    if not ids:
        return Association(
            state="unmatched",
            reason="no_explicit_reference",
            candidates=(),
            selected_passport_id=None,
            model_reference="not_checked",
        )
    if registry is None:
        from pydantic import TypeAdapter

        for identifier in ids:
            TypeAdapter(Digest).validate_python(identifier, strict=True)
        return Association(
            state="ambiguous" if len(ids) > 1 else "declared",
            reason="registry_not_selected",
            candidates=(),
            selected_passport_id=ids[0] if len(ids) == 1 else None,
            model_reference="not_checked",
        )
    checks = tuple(lookup(registry, identifier, manifest.component_kind) for identifier in ids)
    if len(ids) > 1:
        return Association(
            state="conflicted" if manifest.passport_id else "ambiguous",
            reason="multiple_explicit_references",
            candidates=checks,
            selected_passport_id=None,
            model_reference="not_checked",
        )
    check = checks[0]
    state, reason = "declared", "explicit_reference_only"
    if check.status == "invalid":
        state, reason = "conflicted", "invalid_passport_reference"
    if check.identity is not None:
        for key in ("name", "version", "creator", "organization"):
            observed = getattr(manifest.declared_identity, key)
            if observed.origin != "unknown" and observed.value != getattr(check.identity, key):
                state, reason = "conflicted", "declared_identity_differs"
    model_reference = "not_checked"
    if check.status == "consistent" and check.model_id is not None:
        model_reference = lookup(registry, check.model_id, "model").status
        if model_reference == "invalid":
            state, reason = "conflicted", "invalid_model_reference"
    return Association(
        state=state,
        reason=reason,
        candidates=checks,
        selected_passport_id=ids[0] if state == "declared" else None,
        model_reference=model_reference,
    )
