"""Explicit consent, exact preview, manual publication and withdrawal."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..sessions.storage import SessionStore
from .storage import ReportingStore

NOTICE = (
    "Reporting is optional and self-reported. No Forkit account is needed. "
    "Enable records local scan/Passport-creation counts; nothing sends automatically. "
    "Preview includes retained receipts from the current UTC calendar week and three prior weeks, "
    "including receipts from before enable. The report contains counts, calendar dates and a sequence; "
    "requests use a random public profile identifier and a newly generated reporting credential. No Passport IDs, project/file/model names, "
    "prompts, code, chats or existing credentials are included. The collector necessarily sees connection metadata."
)


def configure(commands):
    metrics = commands.add_parser("metrics", help="Optional aggregate reporting; disabled by default, never automatic")
    operations = metrics.add_subparsers(dest="metrics_command", required=True)
    for name in ("status", "enable", "disable", "preview", "send", "withdraw"):
        p = operations.add_parser(name)
        p.add_argument("--store", type=Path, help="Selected local session store and reporting profile")
        if name == "enable":
            p.add_argument("--endpoint", required=True, help="Explicit HTTPS base ending /api/v1/radar")
            p.add_argument("--allow-local-collector", action="store_true", help="Allow explicit HTTP loopback only, for local validation")
        if name == "preview":
            p.add_argument("--output", type=Path, required=True, help="New private exact-payload preview file")
        if name == "send":
            p.add_argument("--preview", type=Path, required=True)
            p.add_argument("--sha256", required=True, help="Exact preview SHA-256 shown by the preview command")


def command(args):
    from . import client

    root = args.store or Path.home() / ".forkit-radar"
    store = ReportingStore(root)
    try:
        operation = args.metrics_command
        if operation == "status":
            print(json.dumps(store.status(), indent=2))
            print("Local features work with reporting disabled. Disabling does not withdraw a previously sent contribution.")
        elif operation == "enable":
            store.enable(args.endpoint, args.allow_local_collector)
            print(NOTICE)
            print("Enabled locally. Next: metrics preview --output preview.json. No network request made.")
        elif operation == "disable":
            store.disable()
            print("Reporting disabled locally. Existing public contribution remains until withdrawal or expiry. Local features continue.")
        elif operation == "preview":
            packet, fingerprint = client.preview(SessionStore(root), store, args.output)
            print(NOTICE)
            print(packet.model_dump_json(indent=2))
            print(f"Exact preview SHA-256: {fingerprint}")
            print("Nothing sent. To publish this exact file, use metrics send --preview FILE --sha256 SHA256 with the same --store.")
        elif operation == "send":
            client.send(store, args.preview, args.sha256)
            print("Collector confirmed this exact aggregate snapshot. Repeated sends do not add another contribution.")
        else:
            client.withdraw(store)
            print("Collector confirmed withdrawal. The contribution no longer enters aggregates; minimal revocation metadata is retained to reject replays.")
        return 0
    except (OSError, ValueError):
        # Parser, path and remote exception details can contain private inputs.
        print("Aggregate operation did not complete. Check consent, the exact preview, collector availability and credentials. Local session features are unaffected.", file=sys.stderr)
        return 2
