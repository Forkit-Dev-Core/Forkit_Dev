"""Ollama's on-disk manifest v2 metadata; never open blobs or probe its API."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path

from ..contracts import Manifest
from ..jsonio import MAX_SAFE_INTEGER, ContractError, load_json
from .metadata import MAX_ENTRIES, candidate, empty_manifest, failure
from .safeio import MetadataError, directory, read_at
from .types import SourceResult, scope_keys

MAX_DIRECTORY_ENTRIES = 256
MODEL_LAYER = "application/vnd.ollama.image.model"


def _descriptor(data):
    if not isinstance(data, dict) or not isinstance(data.get("mediaType"), str):
        raise ContractError("invalid_metadata")
    if not isinstance(data.get("digest"), str) or not re.fullmatch(
        r"sha256:[0-9a-f]{64}", data["digest"]
    ):
        raise ContractError("invalid_metadata")
    size = data.get("size")
    if type(size) is not int or not 0 <= size <= MAX_SAFE_INTEGER:
        raise ContractError("invalid_metadata")
    return data


def parse_manifest(raw: bytes, index: int):
    data = load_json(raw)
    if not isinstance(data, dict):
        raise ContractError("invalid_metadata")
    if type(data.get("schemaVersion")) is not int or data["schemaVersion"] != 2:
        raise ContractError("invalid_metadata")
    if data.get("mediaType") != "application/vnd.docker.distribution.manifest.v2+json":
        raise ContractError("invalid_metadata")
    config = _descriptor(data.get("config"))
    if config["mediaType"] != "application/vnd.docker.container.image.v1+json":
        raise ContractError("invalid_metadata")
    layers = data.get("layers")
    if not isinstance(layers, list) or not 1 <= len(layers) <= 64:
        raise ContractError("invalid_metadata")
    model_layers = [
        layer for layer in map(_descriptor, layers) if layer["mediaType"] == MODEL_LAYER
    ]
    if not 1 <= len(model_layers) <= 4:
        raise ContractError("invalid_metadata")
    size = sum(layer["size"] for layer in model_layers)
    if size > MAX_SAFE_INTEGER:
        raise ContractError("invalid_metadata")
    manifest = empty_manifest("model", dimensions=("identity", "artifacts")).model_dump()
    manifest["artifacts"] = [
        {
            "key": f"model-layer-{i}",
            "kind": "file",
            "hashing_profile": "unknown",
            "digest": {"value": layer["digest"][7:], "origin": "declared"},
        }
        for i, layer in enumerate(model_layers, 1)
    ]
    # Completeness concerns selected manifest descriptors, never actual model bytes.
    manifest["measurement_completeness"]["artifacts"] = "complete"
    return candidate(
        "ollama", index, manifest=Manifest.model_validate(manifest), declared_bytes=size
    )


def ollama(models_root: Path):
    scope = scope_keys("ollama")[0]
    found, unknown = [], 0
    reason = "scoped_metadata_read"
    entries = 0
    deadline = time.monotonic() + 2

    def walk(parent, depth):
        nonlocal entries, unknown, reason
        before = os.fstat(parent)
        with os.scandir(parent) as children:
            for entry in children:
                entries += 1
                if entries > MAX_DIRECTORY_ENTRIES:
                    raise MetadataError("entry_limit")
                if time.monotonic() >= deadline:
                    raise MetadataError("deadline_exceeded")
                try:
                    if entry.is_symlink():
                        raise MetadataError("symlink_or_unsafe_file")
                    if depth < 3:
                        child = os.open(
                            entry.name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=parent
                        )
                        try:
                            yield from walk(child, depth + 1)
                        finally:
                            os.close(child)
                    else:
                        if len(found) >= MAX_ENTRIES:
                            raise MetadataError("result_limit")
                        yield read_at(parent, entry.name, 65_536)
                except MetadataError as exc:
                    if str(exc) in {"entry_limit", "result_limit", "deadline_exceeded"}:
                        raise
                    unknown += 1
                    reason = "entry_invalid"
                except OSError:
                    unknown += 1
                    reason = "entry_invalid"
        after = os.fstat(parent)
        if (before.st_mtime_ns, before.st_ctime_ns) != (after.st_mtime_ns, after.st_ctime_ns):
            unknown += 1
            reason = "metadata_changed"

    try:
        with directory(models_root / "manifests") as root:
            for raw in walk(root, 0):
                try:
                    found.append(parse_manifest(raw, len(found) + 1))
                except (ValueError, TypeError):
                    unknown += 1
                    reason = "entry_invalid"
    except MetadataError as exc:
        unknown += 1
        reason = str(exc)
    except OSError as exc:
        yield failure(scope, exc)
        return
    yield SourceResult(
        scope=scope,
        status="partial" if unknown else "complete",
        reason=reason,
        candidates=found,
        unknown_entries=min(unknown, 4096),
    )
