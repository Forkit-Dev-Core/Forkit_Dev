"""Minimal remote sync bridge for local passport change batches."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlencode
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

    def pull(
        self,
        endpoint: str,
        *,
        source: str | None = None,
        after: int | None = None,
        limit: int = 100,
        passport_type: str | None = None,
        timeout: float = 30.0,
        token: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Pull remote export batches into the local registry without re-emitting them."""
        source_name = source or endpoint
        state_key = f"pull:{source_name}"
        cursor = after if after is not None else self._registry.get_sync_cursor(state_key)
        batches = 0
        items_pulled = 0
        items_applied = 0
        last_response: dict[str, Any] | None = None

        while True:
            exported = self._get_export_batch(
                endpoint,
                after=cursor,
                limit=limit,
                passport_type=passport_type,
                timeout=timeout,
                token=token,
                headers=headers,
            )
            items = exported["items"]
            if not items:
                break

            applied = self._registry.apply_changes(items, record_change=False)
            cursor = exported["cursor"]
            batches += 1
            items_pulled += len(items)
            items_applied += applied["applied"]
            last_response = {
                "status_code": 200,
                "body": exported,
            }
            self._registry.set_sync_cursor(
                state_key,
                cursor,
                endpoint=endpoint,
                metadata={
                    "direction": "pull",
                    "last_batch_size": len(items),
                    "last_applied": applied["applied"],
                    "passport_type": passport_type,
                    "source": source_name,
                },
            )

            if not exported["has_more"]:
                break

        return {
            "source": source_name,
            "state_key": state_key,
            "endpoint": endpoint,
            "cursor": cursor,
            "batches": batches,
            "items_pulled": items_pulled,
            "items_applied": items_applied,
            "status": "synced" if batches else "idle",
            "last_response": last_response,
        }

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

    def _get_export_batch(
        self,
        endpoint: str,
        *,
        after: int,
        limit: int,
        passport_type: str | None,
        timeout: float,
        token: str | None,
        headers: dict[str, str] | None,
    ) -> dict[str, Any]:
        params = {"after": after, "limit": limit}
        if passport_type is not None:
            params["passport_type"] = passport_type
        separator = "&" if "?" in endpoint else "?"
        url = f"{endpoint}{separator}{urlencode(params)}"
        request_headers: dict[str, str] = {}
        if token:
            request_headers["Authorization"] = f"Bearer {token}"
        if headers:
            request_headers.update(headers)

        req = request.Request(url, headers=request_headers, method="GET")
        try:
            with request.urlopen(req, timeout=timeout) as response:
                response_body = response.read().decode("utf-8")
                parsed_body = self._parse_json(response_body)
                if not isinstance(parsed_body, dict):
                    raise RuntimeError("Remote export returned an invalid response.")
                return self._validate_export_batch(parsed_body)
        except error.HTTPError as exc:
            body_text = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Remote pull failed with HTTP {exc.code}: {body_text}"
            ) from exc
        except error.URLError as exc:
            raise RuntimeError(f"Remote pull failed: {exc.reason}") from exc

    @staticmethod
    def _parse_json(raw: str) -> dict[str, Any] | None:
        if not raw.strip():
            return None
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {"raw": raw}
        return data if isinstance(data, dict) else {"data": data}

    @staticmethod
    def _validate_export_batch(payload: dict[str, Any]) -> dict[str, Any]:
        cursor = payload.get("cursor")
        if not isinstance(cursor, int) or cursor < 0:
            raise RuntimeError("Remote export returned an invalid 'cursor'.")

        has_more = payload.get("has_more")
        if not isinstance(has_more, bool):
            raise RuntimeError("Remote export returned an invalid 'has_more' flag.")

        items = payload.get("items")
        if not isinstance(items, list):
            raise RuntimeError("Remote export returned an invalid 'items' list.")

        return {
            "cursor": cursor,
            "has_more": has_more,
            "items": items,
        }
