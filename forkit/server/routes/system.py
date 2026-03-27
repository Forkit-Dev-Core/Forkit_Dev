"""System/bootstrap routes for the local forkit service."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from ... import __version__
from ...registry.local import LocalRegistry
from ..config import ServerSettings
from ..deps import get_registry, get_settings

router = APIRouter(tags=["system"])


@router.get("/")
def service_info(
    settings: ServerSettings = Depends(get_settings),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, object]:
    """Basic service metadata and registry location."""
    return {
        "service": "forkit-local-service",
        "version": __version__,
        "status": "ok",
        "registry": {
            "root": str(settings.registry_root),
            "index_db": str(registry.db_path),
            "lineage_path": str(registry.lineage_path),
            "outbox_path": str(registry.outbox_path),
            "sync_state_path": str(registry.sync_state_path),
        },
        "docs": {
            "openapi": settings.openapi_url,
            "swagger": settings.docs_url,
            "redoc": settings.redoc_url,
        },
    }


@router.get("/healthz")
def health(
    settings: ServerSettings = Depends(get_settings),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, object]:
    """Liveness check for the local service process."""
    return {
        "status": "ok",
        "registry_root": str(settings.registry_root),
        "initialized": registry.models_dir.exists() and registry.agents_dir.exists(),
    }


@router.get("/readyz")
def ready(
    settings: ServerSettings = Depends(get_settings),
    registry: LocalRegistry = Depends(get_registry),
) -> dict[str, object]:
    """Readiness check for the local registry bootstrap."""
    return {
        "status": "ready",
        "registry_root": str(settings.registry_root),
        "index_db_exists": registry.db_path.exists(),
        "models_dir_exists": registry.models_dir.exists(),
        "agents_dir_exists": registry.agents_dir.exists(),
        "outbox_exists": registry.outbox_path.exists(),
        "sync_state_exists": registry.sync_state_path.exists(),
    }
