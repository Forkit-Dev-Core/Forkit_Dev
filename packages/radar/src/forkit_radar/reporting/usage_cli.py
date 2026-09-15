"""New, explicit automatic-count consent; legacy manual consent never upgrades."""

import json
import sys
from pathlib import Path

from ..sessions.storage import SessionStore
from .usage_contracts import POLICY
from .usage_storage import UsageStore, root

NOTICE = """Optional usage-v2 reporting, off by default. Local Forkit needs no account.
After consent, original receipts, scans and Passport creation contribute counts.
During normal use a short-lived worker may send at most once per 24 hours, with
three bounded attempts per snapshot. No background service or historical backfill.
The first receipt is excluded unless you explicitly choose --include-latest.
The snapshot contains 29 daily count rows, fixed tool labels and local distinct
Passport counts. Public windows use 7 or 28 complete UTC days, excluding today.
A random reporting profile and separate credential link updates across projects;
they do not identify a human. Incoming data is pseudonymous, not fully anonymous.
The collector sees connection metadata. No code, prompts, chats, paths, filenames,
project names, Passport/session IDs, source hashes or existing credentials are sent.
Only aggregate cohorts of at least five profiles can appear publicly. This is
opt-in, self-reported coverage; resets/copies/multiple devices affect counts.
Disable stops future attempts; withdrawal removes the live contribution. Neither
can undo already published aggregates or third-party screenshots. Read the
collector's retention/privacy notice before enabling its explicit HTTPS endpoint.
Legacy metrics/Footprints consent is independent and is never converted."""


def configure(commands):
    parser = commands.add_parser(
        "usage", help="Optional automatic count reports; explicit new consent required"
    )
    ops = parser.add_subparsers(dest="usage_command", required=True)
    for name in ("policy", "status", "enable", "disable", "preview", "withdraw"):
        p = ops.add_parser(name)
        if name == "enable":
            p.add_argument("--endpoint", required=True)
            p.add_argument("--consent", required=True, choices=[POLICY])
            p.add_argument(
                "--store", type=Path, help="Session store containing your first useful receipt"
            )
            p.add_argument(
                "--include-latest",
                action="store_true",
                help="Explicitly include only the latest existing receipt",
            )
            p.add_argument(
                "--validation",
                action="store_true",
                help="Exclude this profile from production adoption",
            )
            p.add_argument("--allow-local-collector", action="store_true")


def command(args):
    store = UsageStore(root())
    try:
        op = args.usage_command
        if op == "policy":
            print(NOTICE)
        elif op == "status":
            print(json.dumps(store.status(), indent=2))
        elif op == "enable":
            sessions = SessionStore(args.store or Path.home() / ".forkit-radar")
            latest = sessions.history(limit=1)
            if not latest:
                raise ValueError("first_receipt_required")
            print(NOTICE)
            store.enable(
                args.endpoint,
                consent=args.consent,
                validation=args.validation,
                allow_local=args.allow_local_collector,
            )
            if args.include_latest:
                from .usage_capture import receipt

                receipt(store, sessions, latest[0], include_previous=True)
            print(
                "Consent saved. Nothing sent by this command. Inspect with usage preview; future normal use may report counts."
            )
        elif op == "preview":
            print(store.preview().model_dump_json(indent=2))
        elif op == "disable":
            store.disable()
            print(
                "Usage disabled and queued snapshot canceled. Local features continue. Sent counts remain until withdrawal or expiry."
            )
        else:
            from .usage_worker import begin_withdrawal, supervise

            begin_withdrawal(store)
            if supervise("withdraw") != 0:
                raise ValueError("withdrawal_unconfirmed")
            print(
                "Withdrawal confirmed. Live counts removed; minimal replay-rejection metadata remains."
            )
        return 0
    except (OSError, ValueError):
        print(
            "Usage operation incomplete. Check first receipt, policy, consent, store or collector. Local features are unaffected. If local disabling succeeded, an unconfirmed withdrawal stays disabled. Inspect usage status and retry.",
            file=sys.stderr,
        )
        return 2
