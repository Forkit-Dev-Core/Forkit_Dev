"""Explicit HTTP transport, separated from every local capture command."""
from __future__ import annotations

import hashlib
import http.client
import re
import ssl
from urllib.parse import urlsplit
from uuid import UUID

from ..discovery.safeio import read_metadata
from ..identity.storage import canonical, write_new
from ..jsonio import ContractError, load_json
from .contracts import Preview
from .projection import build

MAX_WIRE = 32_768


def checked_endpoint(value, *, allow_local=False):
    try:
        if type(value) is not str or len(value) > 300 or any(ord(c) < 33 or ord(c) > 126 for c in value):
            raise ValueError
        u = urlsplit(value)
        if u.username is not None or u.password is not None or u.query or u.fragment or u.path != "/api/v1/radar":
            raise ValueError
        if not u.hostname or u.port == 0:
            raise ValueError
        if u.scheme != "https" and not (allow_local and u.scheme == "http" and u.hostname in {"127.0.0.1", "::1"}):
            raise ValueError
        # No redirects, implicit proxies, URL credentials or automatic endpoint selection.
        if "\\" in value or "%" in u.netloc:
            raise ValueError
        return value
    except ValueError:
        raise ContractError("https_collector_endpoint_required") from None


def validate_profile(p):
    keys = {"state", "endpoint", "allow_local", "surface_id", "credential", "sequence", "last_sent_sequence", "journal_complete"}
    try:
        if not isinstance(p, dict) or set(p) != keys:
            raise ValueError
        if p["state"] not in {"enabled", "disabled", "withdrawn"} or type(p["allow_local"]) is not bool or type(p["journal_complete"]) is not bool:
            raise ValueError
        if str(UUID(p["surface_id"], version=4)) != p["surface_id"]:
            raise ValueError
        if not re.fullmatch("[a-f0-9]{64}", p["credential"]):
            raise ValueError
        if any(type(p[k]) is not int or not 0 <= p[k] <= 1_000_000_000 for k in ("sequence", "last_sent_sequence")):
            raise ValueError
        if p["last_sent_sequence"] > p["sequence"]:
            raise ValueError
        checked_endpoint(p["endpoint"], allow_local=p["allow_local"])
        return p
    except (ValueError, TypeError, AttributeError):
        raise ContractError("invalid_reporting_profile") from None


def preview(session_store, reporting_store, destination):
    with reporting_store._connect(write=True) as db:
        profile = reporting_store._profile(db)
        if profile["state"] != "enabled":
            raise ContractError("reporting_disabled")
        if profile["sequence"] >= 1_000_000_000:
            raise ContractError("reporting_sequence_limit")
        profile["sequence"] += 1
        reporting_store._save(db, profile)
    payload = build(session_store, reporting_store, profile["sequence"])
    packet = Preview(endpoint=profile["endpoint"], surface_id=profile["surface_id"],
                     payload_sha256=hashlib.sha256(canonical(payload)).hexdigest(), payload=payload)
    raw = canonical(packet)
    if len(raw) > MAX_WIRE:
        raise ContractError("reporting_payload_limit")
    write_new(destination, raw)
    return packet, hashlib.sha256(raw).hexdigest()


def request(profile, method, payload=None, *, route="surfaces", timeout=8, schema_version="1.0"):
    if route not in {"surfaces", "installations"}:
        raise ContractError("invalid_reporting_route")
    endpoint = checked_endpoint(profile["endpoint"], allow_local=profile["allow_local"])
    u = urlsplit(endpoint)
    connection = (http.client.HTTPSConnection(u.hostname, port=u.port, timeout=timeout, context=ssl.create_default_context())
                  if u.scheme == "https" else http.client.HTTPConnection(u.hostname, port=u.port, timeout=timeout))
    raw = canonical(payload) if payload is not None else b""
    if len(raw) > MAX_WIRE:
        raise ContractError("reporting_payload_limit")
    try:
        connection.request(method, u.path + "/" + route + "/" + profile["surface_id"], body=raw,
                           headers={"Authorization": "Bearer " + profile["credential"],
                                    "Content-Type": "application/json", "Accept": "application/json",
                                    "User-Agent": "Forkit-Radar-aggregate/1"})
        response = connection.getresponse()
        body = response.read(16_385)
        if len(body) > 16_384:
            raise ContractError("collector_response_limit")
        if response.status not in {200, 201, 204}:
            code = {401: "collector_credential_rejected", 409: "collector_sequence_conflict", 410: "collector_surface_withdrawn", 429: "collector_rate_limited", 503: "collector_unavailable"}.get(response.status, "collector_request_rejected")
            raise ContractError(code)
        if method == "DELETE":
            if response.status != 204 or body:
                raise ContractError("invalid_withdrawal_confirmation")
            return
        value = load_json(body)
        if set(value) != {"schema_version", "status", "accepted_sequence", "payload_sha256"} or value["schema_version"] != schema_version or value["status"] not in ("stored", "unchanged") or type(value["accepted_sequence"]) is not int or value["accepted_sequence"] != payload.sequence or value["payload_sha256"] != hashlib.sha256(raw).hexdigest():
            raise ContractError("invalid_publication_confirmation")
    except (OSError, http.client.HTTPException, ValueError) as error:
        if isinstance(error, ContractError):
            raise
        raise ContractError("collector_connection_failed_retry_same_preview") from None
    finally:
        connection.close()


def send(reporting_store, source, expected_sha256):
    raw = read_metadata(source.absolute())
    if len(raw) > MAX_WIRE or not re.fullmatch("[a-f0-9]{64}", expected_sha256) or hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ContractError("preview_digest_mismatch")
    packet = Preview.model_validate(load_json(raw))
    if canonical(packet) != raw or hashlib.sha256(canonical(packet.payload)).hexdigest() != packet.payload_sha256:
        raise ContractError("invalid_canonical_preview")
    with reporting_store._connect() as db:
        p = reporting_store._profile(db)
    if p["state"] != "enabled":
        raise ContractError("reporting_disabled")
    if (packet.endpoint, packet.surface_id) != (p["endpoint"], p["surface_id"]) or packet.payload.sequence > p["sequence"]:
        raise ContractError("preview_profile_mismatch")
    request(p, "PUT", packet.payload)
    with reporting_store._connect(write=True) as db:
        current = reporting_store._profile(db)
        if current["surface_id"] == p["surface_id"]:
            current["last_sent_sequence"] = max(current["last_sent_sequence"], packet.payload.sequence)
            reporting_store._save(db, current)


def withdraw(reporting_store):
    with reporting_store._connect() as db:
        p = reporting_store._profile(db)
    # Keep the credential until confirmed so interrupted withdrawals can retry.
    request(p, "DELETE")
    with reporting_store._connect(write=True) as db:
        current = reporting_store._profile(db)
        if current["surface_id"] == p["surface_id"]:
            current["state"] = "withdrawn"
            reporting_store._save(db, current)
