"""Configuration for the local forkit service."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

VALID_SYNC_BACKENDS = {"local", "postgres"}


@dataclass(slots=True)
class ServerSettings:
    """Runtime settings for the local FastAPI service."""

    registry_root: Path = Path("~/.forkit/registry").expanduser().resolve()
    host: str = "127.0.0.1"
    port: int = 8000
    title: str = "forkit local service"
    description: str = "Local HTTP service for the forkit passport registry."
    docs_url: str = "/docs"
    redoc_url: str = "/redoc"
    openapi_url: str = "/openapi.json"
    sync_backend: str = "local"
    sync_postgres_dsn: str | None = None
    sync_postgres_schema: str = "public"
    sync_bearer_token: str | None = None

    def __post_init__(self) -> None:
        self.sync_backend = self.sync_backend.lower()
        if self.sync_backend not in VALID_SYNC_BACKENDS:
            supported = ", ".join(sorted(VALID_SYNC_BACKENDS))
            raise ValueError(
                f"Unsupported sync backend '{self.sync_backend}'. Expected one of: {supported}."
            )

    @classmethod
    def from_env(cls) -> "ServerSettings":
        """Build settings from environment variables when present."""
        registry_root = Path(
            os.getenv("FORKIT_REGISTRY_ROOT", "~/.forkit/registry")
        ).expanduser().resolve()
        host = os.getenv("FORKIT_SERVER_HOST", "127.0.0.1")
        port = int(os.getenv("FORKIT_SERVER_PORT", "8000"))
        return cls(
            registry_root=registry_root,
            host=host,
            port=port,
            sync_backend=os.getenv("FORKIT_SYNC_BACKEND", "local"),
            sync_postgres_dsn=os.getenv("FORKIT_SYNC_POSTGRES_DSN"),
            sync_postgres_schema=os.getenv("FORKIT_SYNC_POSTGRES_SCHEMA", "public"),
            sync_bearer_token=os.getenv("FORKIT_SYNC_BEARER_TOKEN"),
        )
