"""Passport registration routes for the local forkit service."""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from ...domain.hashing import HashEngine
from ...domain.lineage import LineageNode, NodeType
from ...registry.local import LocalRegistry
from ...schemas import AgentPassport, ModelPassport
from ..deps import get_registry

try:
    from pydantic import ValidationError
except ImportError:  # pragma: no cover - FastAPI installs pydantic in practice
    ValidationError = ValueError  # type: ignore[assignment]

router = APIRouter(tags=["passports"])


def _validation_error(exc: Exception) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        detail=str(exc),
    )


def _error_response(
    *,
    status_code: int,
    code: str,
    message: str,
    passport_id: str,
    **extra: Any,
) -> JSONResponse:
    payload: dict[str, Any] = {
        "error": {
            "code": code,
            "message": message,
            "passport_id": passport_id,
        }
    }
    if extra:
        payload["error"].update(extra)
    return JSONResponse(status_code=status_code, content=payload)


def _normalise_agent_payload(payload: dict[str, Any]) -> dict[str, Any]:
    data = dict(payload)
    system_prompt = data.get("system_prompt")
    if isinstance(system_prompt, str):
        data["system_prompt"] = {
            "hash": HashEngine.hash_system_prompt(system_prompt),
            "length_chars": len(system_prompt),
        }
    return data


def _node_from_passport(passport: ModelPassport | AgentPassport) -> dict[str, Any]:
    passport_dict = passport.to_dict()
    node_type = NodeType.AGENT if isinstance(passport, AgentPassport) else NodeType.MODEL
    metadata: dict[str, Any] = {"creator": passport_dict.get("creator", {})}
    if isinstance(passport, AgentPassport):
        metadata["role"] = passport_dict.get("role")
    node = LineageNode(
        id=passport.id,
        node_type=node_type,
        name=passport.name,
        version=passport.version,
        metadata=metadata,
    )
    return node.to_dict()


@router.post("/models", status_code=status.HTTP_201_CREATED)
def register_model(
    payload: dict[str, Any] = Body(...),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Create and persist a model passport in the local registry."""
    try:
        passport = ModelPassport.from_dict(payload)
    except (ValidationError, ValueError, TypeError) as exc:
        raise _validation_error(exc) from exc

    registry.register_model(passport)
    return passport.to_dict()


@router.post("/agents", status_code=status.HTTP_201_CREATED)
def register_agent(
    payload: dict[str, Any] = Body(...),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Create and persist an agent passport in the local registry."""
    try:
        passport = AgentPassport.from_dict(_normalise_agent_payload(payload))
    except (ValidationError, ValueError, TypeError) as exc:
        raise _validation_error(exc) from exc

    registry.register_agent(passport)
    return passport.to_dict()


@router.get("/passports/{passport_id}", response_model=None)
def get_passport(
    passport_id: str,
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any] | JSONResponse:
    """Retrieve any stored passport by ID."""
    passport = registry.get(passport_id)
    if passport is None:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Passport not found.",
            passport_id=passport_id,
        )
    return passport.to_dict()


@router.post("/verify/{passport_id}", response_model=None)
def verify_passport(
    passport_id: str,
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any] | JSONResponse:
    """Verify a stored passport against its deterministic ID."""
    result = registry.verify_passport(passport_id)
    if result.get("reason") == "not_found":
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Passport not found.",
            passport_id=passport_id,
        )
    if not result.get("valid"):
        return _error_response(
            status_code=status.HTTP_409_CONFLICT,
            code=result.get("reason", "invalid"),
            message="Stored passport does not match its derived identity.",
            passport_id=passport_id,
            verification=result,
        )
    return result


@router.get("/lineage/{passport_id}", response_model=None)
def get_lineage(
    passport_id: str,
    direction: Literal["ancestors", "descendants", "both"] = Query(
        "both",
        description="Which lineage directions to include.",
    ),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any] | JSONResponse:
    """Return lineage data for a stored passport."""
    passport = registry.get(passport_id)
    if passport is None:
        return _error_response(
            status_code=status.HTTP_404_NOT_FOUND,
            code="not_found",
            message="Passport not found.",
            passport_id=passport_id,
        )

    graph = registry.lineage
    node = graph.get_node(passport_id)
    ancestors = graph.ancestors(passport_id) if direction in ("ancestors", "both") else []
    descendants = graph.descendants(passport_id) if direction in ("descendants", "both") else []

    return {
        "node": node.to_dict() if node is not None else _node_from_passport(passport),
        "direction": direction,
        "ancestors": [ancestor.to_dict() for ancestor in ancestors],
        "descendants": [descendant.to_dict() for descendant in descendants],
    }


@router.get("/export")
def export_passports(
    after: int = Query(
        0,
        ge=0,
        description="Return only changes with a cursor greater than this value.",
    ),
    limit: int = Query(
        100,
        ge=1,
        le=1000,
        description="Maximum number of change records to return.",
    ),
    passport_type: Literal["model", "agent"] | None = Query(
        None,
        description="Optional passport type filter.",
    ),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, Any]:
    """Export cursor-ordered passport changes for external sync."""
    return registry.export_changes(
        after=after,
        limit=limit,
        passport_type=passport_type,
    )
