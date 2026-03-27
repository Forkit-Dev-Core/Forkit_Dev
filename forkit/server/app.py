"""FastAPI app factory for the local forkit service."""

from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from .. import __version__
from ..registry.local import LocalRegistry
from .config import ServerSettings
from .routes.passports import router as passports_router
from .routes.sync import router as sync_router
from .routes.system import router as system_router
from .sync_store import LocalSyncStore, PostgresSyncStore, SyncStore


def create_app(
    settings: ServerSettings | None = None,
    registry: LocalRegistry | None = None,
    sync_store: SyncStore | None = None,
) -> FastAPI:
    """Create the local HTTP service app."""
    resolved_settings = settings or ServerSettings.from_env()
    resolved_registry = registry or LocalRegistry(root=resolved_settings.registry_root)
    if sync_store is None:
        if resolved_settings.sync_backend == "postgres":
            if not resolved_settings.sync_postgres_dsn:
                raise ValueError(
                    "FORKIT_SYNC_POSTGRES_DSN is required when sync_backend is 'postgres'."
                )
            resolved_sync_store: SyncStore = PostgresSyncStore(
                resolved_settings.sync_postgres_dsn,
                schema=resolved_settings.sync_postgres_schema,
            )
        else:
            resolved_sync_store = LocalSyncStore(resolved_registry)
    else:
        resolved_sync_store = sync_store

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        resolved_registry.init()
        app.state.settings = resolved_settings
        app.state.registry = resolved_registry
        app.state.sync_store = resolved_sync_store
        yield

    app = FastAPI(
        title=resolved_settings.title,
        description=resolved_settings.description,
        version=__version__,
        docs_url=resolved_settings.docs_url,
        redoc_url=resolved_settings.redoc_url,
        openapi_url=resolved_settings.openapi_url,
        lifespan=lifespan,
    )
    app.include_router(system_router)
    app.include_router(passports_router)
    app.include_router(sync_router)
    return app
