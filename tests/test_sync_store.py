"""Tests for sync receiver store backends."""

from __future__ import annotations

from typing import Any

import pytest

from forkit.server.sync_store import PostgresSyncStore


MODEL_ID = "m" * 64


class FakeCursor:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state
        self._fetchone: tuple[Any, ...] | None = None

    def execute(self, sql: str, params: tuple[Any, ...] | None = None) -> None:
        params = params or ()
        compact = " ".join(sql.split())

        if compact.startswith('CREATE SCHEMA') or compact.startswith('CREATE TABLE'):
            self._fetchone = None
            return

        if 'INSERT INTO "public"."forkit_sync_batches"' in compact:
            key = (params[0], params[1])
            if key in self._state["batches"]:
                self._fetchone = None
            else:
                self._state["batches"][key] = {
                    "received_at": params[5],
                    "envelope_json": params[6],
                }
                self._fetchone = (params[5],)
            return

        if 'SELECT received_at FROM "public"."forkit_sync_batches"' in compact:
            key = (params[0], params[1])
            batch = self._state["batches"].get(key)
            self._fetchone = (batch["received_at"],) if batch is not None else None
            return

        if 'INSERT INTO "public"."forkit_sync_items"' in compact:
            key = (params[0], params[1], params[2], params[3])
            self._state["items"][key] = {
                "passport_type": params[4],
                "changed_at": params[5],
                "document_json": params[6],
                "received_at": params[7],
            }
            self._fetchone = None
            return

        if 'INSERT INTO "public"."forkit_sync_passports"' in compact:
            self._state["passports"][params[0]] = {
                "passport_type": params[1],
                "latest_target": params[2],
                "latest_source": params[3],
                "latest_operation": params[4],
                "latest_cursor": params[5],
                "latest_changed_at": params[6],
                "latest_document_json": params[7],
                "updated_at": params[8],
            }
            self._fetchone = None
            return

        raise AssertionError(f"Unexpected SQL: {compact}")

    def fetchone(self) -> tuple[Any, ...] | None:
        return self._fetchone

    def __enter__(self) -> "FakeCursor":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class FakeConnection:
    def __init__(self, state: dict[str, Any]) -> None:
        self._state = state

    def cursor(self) -> FakeCursor:
        return FakeCursor(self._state)

    def __enter__(self) -> "FakeConnection":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class TestPostgresSyncStore:
    def test_invalid_schema_name_is_rejected(self):
        with pytest.raises(ValueError, match="simple SQL identifier"):
            PostgresSyncStore("postgresql://demo", schema="bad-schema")

    def test_ingest_sync_batch_is_idempotent_by_target_and_cursor(self):
        state = {"batches": {}, "items": {}, "passports": {}}
        store = PostgresSyncStore(
            "postgresql://demo",
            connect_factory=lambda dsn: FakeConnection(state),
        )
        envelope = {
            "source": "local-dev",
            "target": "main-server",
            "after": 0,
            "cursor": 1,
            "has_more": False,
            "items": [
                {
                    "cursor": 1,
                    "operation": "upsert",
                    "passport_id": MODEL_ID,
                    "passport_type": "model",
                    "changed_at": "2026-03-27T12:00:00+00:00",
                    "document": {"id": MODEL_ID, "passport_type": "model"},
                }
            ],
        }

        first = store.ingest_sync_batch(envelope)
        second = store.ingest_sync_batch(envelope)

        assert first["status"] == "accepted"
        assert second["status"] == "duplicate"
        assert first["idempotency_key"] == "main-server:1"
        assert len(state["batches"]) == 1
        assert len(state["items"]) == 1
        assert state["passports"][MODEL_ID]["latest_target"] == "main-server"
