"""Reference sync receiver routes for generic passport change batches."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, status

from ...registry.local import LocalRegistry
from ..deps import get_registry

router = APIRouter(tags=["sync"])


def _validation_error(message: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=message,
    )


def _validate_sync_item(item: Any, index: int) -> dict[str, Any]:
    if not isinstance(item, dict):
        raise _validation_error(f"'items[{index}]' must be an object.")

    operation = item.get("operation")
    if operation not in {"upsert", "delete"}:
        raise _validation_error(f"'items[{index}].operation' must be 'upsert' or 'delete'.")

    passport_id = item.get("passport_id")
    if not isinstance(passport_id, str) or not passport_id:
        raise _validation_error(f"'items[{index}].passport_id' must be a non-empty string.")

    passport_type = item.get("passport_type")
    if passport_type not in {"model", "agent"}:
        raise _validation_error(f"'items[{index}].passport_type' must be 'model' or 'agent'.")

    cursor = item.get("cursor")
    if not isinstance(cursor, int) or cursor < 1:
        raise _validation_error(f"'items[{index}].cursor' must be an integer greater than 0.")

    changed_at = item.get("changed_at")
    if not isinstance(changed_at, str) or not changed_at:
        raise _validation_error(f"'items[{index}].changed_at' must be a non-empty string.")

    document = item.get("document")
    if operation == "upsert" and not isinstance(document, dict):
        raise _validation_error(f"'items[{index}].document' must be an object for upserts.")
    if operation == "delete" and document is not None and not isinstance(document, dict):
        raise _validation_error(f"'items[{index}].document' must be null or an object for deletes.")

    return dict(item)


def _validate_sync_envelope(payload: Any) -> dict[str, Any]:
    if not isinstance(payload, dict):
        raise _validation_error("Sync payload must be an object.")

    source = payload.get("source")
    if not isinstance(source, str) or not source:
        raise _validation_error("'source' must be a non-empty string.")

    target = payload.get("target")
    if not isinstance(target, str) or not target:
        raise _validation_error("'target' must be a non-empty string.")

    after = payload.get("after")
    if not isinstance(after, int) or after < 0:
        raise _validation_error("'after' must be an integer greater than or equal to 0.")

    cursor = payload.get("cursor")
    if not isinstance(cursor, int) or cursor < after:
        raise _validation_error("'cursor' must be an integer greater than or equal to 'after'.")

    has_more = payload.get("has_more")
    if not isinstance(has_more, bool):
        raise _validation_error("'has_more' must be a boolean.")

    items = payload.get("items")
    if not isinstance(items, list):
        raise _validation_error("'items' must be a list.")

    return {
        "source": source,
        "target": target,
        "after": after,
        "cursor": cursor,
        "has_more": has_more,
        "items": [_validate_sync_item(item, index) for index, item in enumerate(items)],
    }


@router.post("/sync/passports", status_code=status.HTTP_202_ACCEPTED)
def receive_sync_batch(
    payload: dict[str, Any] = Body(...),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Receive and persist a generic passport change batch for later processing."""
    envelope = _validate_sync_envelope(payload)
    return registry.ingest_sync_batch(envelope)
