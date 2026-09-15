"""Deadline and output containment for fixed installed collector workers."""

from __future__ import annotations

import json
import os
import selectors
import subprocess
import sys
import time

from pydantic import ValidationError

from ..jsonio import ContractError, load_json
from .types import Detector, SourceResult, scope_keys

WORKER_SECONDS = 3.0
MAX_OUTPUT_BYTES = 262_144


def _run_command(command: list[str], timeout: float) -> tuple[bytes, str | None]:
    """Private execution helper, only fixed Radar commands in the product path.

    Drain stdout incrementally; never collect stderr. Deadline includes reading
    and waiting. Kill/reap only our worker, with a bounded cleanup interval.
    This is not a hostile-code sandbox or an OS scheduling guarantee.
    """
    deadline = time.monotonic() + timeout
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd="/",
            close_fds=True,
        )
    except OSError:
        return b"", "collector_failed"
    output = bytearray()
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return bytes(output), "deadline_exceeded"
                for key, _ in selector.select(remaining):
                    chunk = os.read(key.fileobj.fileno(), 32_768)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    if len(output) + len(chunk) > MAX_OUTPUT_BYTES:
                        return b"", "worker_output_limit"
                    output.extend(chunk)
        remaining = max(0.001, deadline - time.monotonic())
        try:
            return_code = process.wait(timeout=remaining)
        except subprocess.TimeoutExpired:
            return bytes(output), "deadline_exceeded"
        return bytes(output), None if return_code == 0 else "collector_failed"
    except OSError:
        return b"", "collector_failed"
    finally:
        if process.poll() is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass  # It exited after poll().
            try:
                process.wait(timeout=0.2)
            except subprocess.TimeoutExpired:
                pass  # An uninterruptible kernel wait must not hang the caller.
        process.stdout.close()


def run_worker(
    detector: Detector, *, timeout: float = WORKER_SECONDS, options: dict[str, str] | None = None
) -> tuple[SourceResult, ...]:
    expected = scope_keys(detector)
    command = [sys.executable, "-I", "-B", "-m", "forkit_radar.discovery.worker", detector]
    if options:
        command.append(json.dumps(options))
    raw, failure = _run_command(command, timeout)
    found = {}
    try:
        # A killed worker may leave an unfinished last line; never parse it.
        lines = raw.split(b"\n")
        if lines[-1] and failure is None:
            raise ContractError("invalid_worker_output")
        for line in lines[:-1]:
            result = SourceResult.model_validate(load_json(line))
            if result.scope not in expected or result.scope in found:
                raise ContractError("invalid_worker_output")
            found[result.scope] = result
    except (ContractError, ValidationError, ValueError):
        found = {}
        failure = "invalid_worker_output"
    # Successful completed scopes survive a later timeout/crash in another scope.
    # A missing result is explicit failure, never an empty successful inventory.
    missing_reason = failure or "invalid_worker_output"
    status = "timeout" if missing_reason == "deadline_exceeded" else "malformed"
    return tuple(
        found.get(key)
        or SourceResult(scope=key, status=status, reason=missing_reason, candidates=())
        for key in expected
    )
