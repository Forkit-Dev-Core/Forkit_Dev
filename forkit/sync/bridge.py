"""Minimal remote sync bridge for local passport change batches."""

from __future__ import annotations

import json
from typing import Any
from urllib import error, request

from ..registry import LocalRegistry


class RemoteSyncBridge:
    """Push cursor-ordered local changes to a generic remote HTTP endpoint."""

    def __init__(self, registry: LocalRegistry) -> None:
        self._registry = registry

    def push(
        self,
        endpoint: str,
        *,
        target: str | None = None,
        after: int | None = None,
        limit: int = 100,
        passport_type: str | None = None,
        timeout: float = 30.0,
        token: str | None = None,
        source: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Push local outbox batches to a remote endpoint and advance the local cursor."""
        target_name = target or endpoint
        cursor = after if after is not None else self._registry.get_sync_cursor(target_name)
        batches = 0
        items_pushed = 0
        last_response: dict[str, Any] | None = None

        while True:
            exported = self._registry.export_changes(
                after=cursor,
                limit=limit,
                passport_type=passport_type,
            )
            items = exported["items"]
            if not items:
                break

            payload = {
                "source": source or str(self._registry.root),
                "target": target_name,
                "after": cursor,
                "cursor": exported["cursor"],
                "has_more": exported["has_more"],
                "items": items,
            }
            last_response = self._post_batch(
                endpoint,
                payload,
                timeout=timeout,
                token=token,
                headers=headers,
            )
            cursor = exported["cursor"]
            batches += 1
            items_pushed += len(items)
            self._registry.set_sync_cursor(
                target_name,
                cursor,
                endpoint=endpoint,
                metadata={
                    "last_batch_size": len(items),
                    "last_response_status": last_response["status_code"],
                    "passport_type": passport_type,
                },
            )

            if not exported["has_more"]:
                break

        return {
            "target": target_name,
            "endpoint": endpoint,
            "cursor": cursor,
            "batches": batches,
            "items_pushed": items_pushed,
            "status": "synced" if batches else "idle",
            "last_response": last_response,
        }

    def status(self) -> dict[str, Any]:
        """Return persisted sync cursor state for all known targets."""
        return self._registry.get_sync_state()

    def _post_batch(
        self,
        endpoint: str,
        payload: dict[str, Any],
        *,
        timeout: float,
        token: str | None,
        headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        request_headers = {"Content-Type": "application/json"}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)

        req = request.Request(endpoint, data=body, headers=request_headers, method="POST")
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")
                parsed_body = self._parse_json(response_body)
                return {
                    "status_code": response.status,
                    "body": parsed_body,
                }
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Remote sync failed with HTTP {exc.code}: {body_text}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Remote sync failed: {exc.reason}") from exc

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        if not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        return data if isinstance(data, dict) else {"data": data}
