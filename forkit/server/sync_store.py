"""Sync receiver backends for local and Postgres-backed ingestion."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import re
from typing import Any, Callable, Protocol

from ..registry.local import LocalRegistry

_IDENTIFIER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


class SyncStore(Protocol):
    """Abstract sync batch receiver backend."""

    def ingest_sync_batch(self, envelope: dict[str, Any]) -> dict[str, Any]:
        """Persist an incoming sync envelope and return a stable ack."""


class LocalSyncStore:
    """Reference local-file receiver backend."""

    def __init__(self, registry: LocalRegistry) -> None:
        self._registry = registry

    def ingest_sync_batch(self, envelope: dict[str, Any]) -> dict[str, Any]:
        return self._registry.ingest_sync_batch(envelope)


class PostgresSyncStore:
    """Postgres-backed sync receiver with idempotent batch ingest."""

    def __init__(
        self,
        dsn: str,
        *,
        schema: str = "public",
        connect_factory: Callable[[str], Any] | None = None,
    ) -> None:
        if not dsn:
            raise ValueError("Postgres sync backend requires a non-empty DSN.")
        if not _IDENTIFIER_RE.fullmatch(schema):
            raise ValueError(
                "Postgres sync schema must be a simple SQL identifier "
                "(letters, numbers, underscores; cannot start with a number)."
            )
        self._dsn = dsn
        self._schema = schema
        self._connect_factory = connect_factory or self._default_connect_factory()

    def ingest_sync_batch(self, envelope: dict[str, Any]) -> dict[str, Any]:
        received_at = datetime.now(timezone.utc).isoformat()
        accepted = len(envelope["items"])
        stored_passports = len({str(item["passport_id"]) for item in envelope["items"]})

        with self._connect_factory(self._dsn) as connection:
            with connection.cursor() as cursor:
                self._ensure_schema(cursor)
                inserted = self._insert_batch(cursor, envelope, received_at)
                if inserted:
                    for item in envelope["items"]:
                        self._insert_item(cursor, envelope, item, received_at)
                        self._upsert_passport(cursor, envelope, item, received_at)
                else:
                    received_at = self._fetch_received_at(cursor, envelope) or received_at

        return {
            "status": "accepted" if inserted else "duplicate",
            "source": envelope["source"],
            "target": envelope["target"],
            "cursor": envelope["cursor"],
            "accepted": accepted,
            "stored_passports": stored_passports,
            "received_at": received_at,
            "idempotency_key": f"{envelope['target']}:{envelope['cursor']}",
        }

    @staticmethod
    def _default_connect_factory() -> Callable[[str], Any]:
        try:
            import psycopg
        except ImportError as exc:  # pragma: no cover - depends on optional extra
            raise RuntimeError(
                "Postgres sync backend requires the optional dependency. "
                "Install with 'forkit-core[postgres]'."
            ) from exc
        return psycopg.connect

    def _ensure_schema(self, cursor: Any) -> None:
        cursor.execute(f'CREATE SCHEMA IF NOT EXISTS "{self._schema}"')
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self._schema}"."forkit_sync_batches" (
                id BIGSERIAL PRIMARY KEY,
                target TEXT NOT NULL,
                cursor BIGINT NOT NULL,
                source TEXT NOT NULL,
                after_cursor BIGINT NOT NULL,
                has_more BOOLEAN NOT NULL,
                received_at TIMESTAMPTZ NOT NULL,
                envelope_json JSONB NOT NULL,
                UNIQUE (target, cursor)
            )
            """
        )
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self._schema}"."forkit_sync_items" (
                id BIGSERIAL PRIMARY KEY,
                target TEXT NOT NULL,
                cursor BIGINT NOT NULL,
                passport_id TEXT NOT NULL,
                operation TEXT NOT NULL,
                passport_type TEXT NOT NULL,
                changed_at TEXT NOT NULL,
                document_json JSONB NULL,
                received_at TIMESTAMPTZ NOT NULL,
                UNIQUE (target, cursor, passport_id, operation)
            )
            """
        )
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS "{self._schema}"."forkit_sync_passports" (
                passport_id TEXT PRIMARY KEY,
                passport_type TEXT NOT NULL,
                latest_target TEXT NOT NULL,
                latest_source TEXT NOT NULL,
                latest_operation TEXT NOT NULL,
                latest_cursor BIGINT NOT NULL,
                latest_changed_at TEXT NOT NULL,
                latest_document_json JSONB NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """
        )

    def _insert_batch(self, cursor: Any, envelope: dict[str, Any], received_at: str) -> bool:
        cursor.execute(
            f"""
            INSERT INTO "{self._schema}"."forkit_sync_batches" (
                target,
                cursor,
                source,
                after_cursor,
                has_more,
                received_at,
                envelope_json
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
            ON CONFLICT (target, cursor) DO NOTHING
            RETURNING received_at
            """,
            (
                envelope["target"],
                envelope["cursor"],
                envelope["source"],
                envelope["after"],
                envelope["has_more"],
                received_at,
                json.dumps(envelope, sort_keys=True),
            ),
        )
        return cursor.fetchone() is not None

    def _fetch_received_at(self, cursor: Any, envelope: dict[str, Any]) -> str | None:
        cursor.execute(
            f"""
            SELECT received_at
            FROM "{self._schema}"."forkit_sync_batches"
            WHERE target = %s AND cursor = %s
            """,
            (envelope["target"], envelope["cursor"]),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return str(row[0])

    def _insert_item(
        self,
        cursor: Any,
        envelope: dict[str, Any],
        item: dict[str, Any],
        received_at: str,
    ) -> None:
        document = item.get("document")
        document_json = json.dumps(document, sort_keys=True) if document is not None else None
        cursor.execute(
            f"""
            INSERT INTO "{self._schema}"."forkit_sync_items" (
                target,
                cursor,
                passport_id,
                operation,
                passport_type,
                changed_at,
                document_json,
                received_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (target, cursor, passport_id, operation) DO NOTHING
            """,
            (
                envelope["target"],
                envelope["cursor"],
                item["passport_id"],
                item["operation"],
                item["passport_type"],
                item["changed_at"],
                document_json,
                received_at,
            ),
        )

    def _upsert_passport(
        self,
        cursor: Any,
        envelope: dict[str, Any],
        item: dict[str, Any],
        received_at: str,
    ) -> None:
        document = item.get("document")
        document_json = json.dumps(document, sort_keys=True) if document is not None else None
        cursor.execute(
            f"""
            INSERT INTO "{self._schema}"."forkit_sync_passports" (
                passport_id,
                passport_type,
                latest_target,
                latest_source,
                latest_operation,
                latest_cursor,
                latest_changed_at,
                latest_document_json,
                updated_at
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
            ON CONFLICT (passport_id) DO UPDATE SET
                passport_type = EXCLUDED.passport_type,
                latest_target = EXCLUDED.latest_target,
                latest_source = EXCLUDED.latest_source,
                latest_operation = EXCLUDED.latest_operation,
                latest_cursor = EXCLUDED.latest_cursor,
                latest_changed_at = EXCLUDED.latest_changed_at,
                latest_document_json = EXCLUDED.latest_document_json,
                updated_at = EXCLUDED.updated_at
            """,
            (
                item["passport_id"],
                item["passport_type"],
                envelope["target"],
                envelope["source"],
                item["operation"],
                envelope["cursor"],
                item["changed_at"],
                document_json,
                received_at,
            ),
        )
