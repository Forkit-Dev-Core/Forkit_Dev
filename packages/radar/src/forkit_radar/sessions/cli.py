"""Account-free local session commands; execution requires an explicit argv."""

from __future__ import annotations

import json
import os
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path

from ..jsonio import ContractError
from .details import ReceiptV2, Selection
from .models import TOOL_NAMES, Receipt
from .storage import SessionStore


def configure(commands):
    session = commands.add_parser(
        "session", help="Capture an explicit local coding session; no account needed"
    )
    actions = session.add_subparsers(dest="session_action", required=True)
    operations = [(action, actions.add_parser(action)) for action in ("start", "run", "stop", "recover", "active")]
    for action in ("start", "stop"):
        shortcut = commands.add_parser(action, help="Start a local session" if action == "start" else "Finish the manual session in this Git project")
        shortcut.set_defaults(command="session", session_action=action)
        operations.append((action, shortcut))
    for action, operation in operations:
        operation.add_argument("--store", type=Path)
        operation.add_argument(
            "--json", action="store_true", help="Private local JSON, not a public share payload"
        )
        if action in {"start", "run"}:
            operation.add_argument(
                "--project", type=Path, help="Selected Git root; defaults to current directory"
            )
            operation.add_argument(
                "--tool",
                choices=tuple(TOOL_NAMES),
                required=True,
                help="Your tool selection; not an authenticated identity",
            )
            operation.add_argument(
                "--agent-manifest",
                type=Path,
                help="Explicit agent metadata file; never import or run it",
            )
            operation.add_argument(
                "--registry", type=Path, help="Existing local Core registry to read; no account"
            )
            operation.add_argument(
                "--passport-id",
                help="Explicit existing agent Passport ID; association remains declared",
            )
        if action == "run":
            import argparse

            operation.add_argument(
                "argv",
                nargs=argparse.REMAINDER,
                help="-- followed by the command you explicitly want to run",
            )
        if action in {"stop", "recover"}:
            operation.add_argument("session_id", **({"nargs": "?"} if action == "stop" else {}))
            if action == "stop":
                operation.add_argument("--project", type=Path, help="Git root for automatic selection when the session ID is omitted")
            operation.add_argument(
                "--files", action="store_true", help="Show private project-relative filenames"
            )
    receipt = commands.add_parser("receipt", help="Show a saved local Session Receipt")
    receipt.add_argument("session_id", nargs="?")
    receipt.add_argument("--store", type=Path)
    receipt.add_argument(
        "--json", action="store_true", help="Includes private project-relative paths"
    )
    receipt.add_argument("--files", action="store_true")
    history = commands.add_parser(
        "history", help="Show recent local session receipts; no account needed"
    )
    history.add_argument("--store", type=Path)
    history.add_argument(
        "--json", action="store_true", help="Includes private project-relative paths"
    )
    history.add_argument("--limit", type=int, default=20)
    card = commands.add_parser("card", help="Generate a local aggregate share card; no upload/account")
    card.add_argument("session_id", nargs="?")
    card.add_argument("--store", type=Path)
    destination = card.add_mutually_exclusive_group(required=True)
    destination.add_argument("--output", type=Path, help="New .html (PNG export), .svg or .json file")
    destination.add_argument("--json", action="store_true", help="Public aggregate JSON to stdout")
    for name, description in (
        ("view", "Generate a private offline history view; no server or account"),
        ("summary", "Daily/weekly meaningful changes from retained local receipts"),
        ("summary-card", "Export a local aggregate daily/weekly share card"),
    ):
        operation = commands.add_parser(name, help=description)
        operation.add_argument("--store", type=Path)
        operation.add_argument("--timezone", help="IANA timezone, e.g. Europe/Berlin; defaults to system local rules")
        operation.add_argument("--project-id", help="Select one exact local project ID from your receipt")
        if name == "view":
            operation.add_argument("--limit", type=int, default=200, help="Timeline entries, 1–1000; calendar totals still use all receipts")
        if name in {"summary", "summary-card"}:
            operation.add_argument("--period", choices=("today", "week", "history") if name == "summary" else ("today", "week"), default="week")
        if name == "summary":
            operation.add_argument("--json", action="store_true", help="Private summary JSON")
        else:
            destination = operation.add_mutually_exclusive_group(required=True)
            destination.add_argument("--output", type=Path, help="New private .html file" if name == "view" else "New aggregate .html, .svg or .json file")
            destination.add_argument("--json", action="store_true", help="Private view JSON" if name == "view" else "Public aggregate card JSON")
    storage = commands.add_parser("storage", help="Local session capacity, private backup and explicit snapshot compaction")
    maintenance = storage.add_subparsers(dest="storage_action", required=True)
    for name in ("status", "backup", "compact", "recover"):
        action = maintenance.add_parser(name)
        action.add_argument("--store", type=Path)
        action.add_argument("--json", action="store_true")
        if name == "backup":
            action.add_argument("--output", type=Path, required=True, help="New private SQLite backup; never share publicly")
        if name == "compact":
            action.add_argument("--keep", type=int, default=20, help="Retain latest 1–100 after snapshots per project; default 20")
            action.add_argument("--apply", action="store_true", help="Explicitly remove old snapshots; without this flag, preview only. All receipts and active baselines remain.")


def duration(milliseconds: int | None) -> str:
    if milliseconds is None:
        return "duration unknown"
    seconds = milliseconds // 1000
    if seconds < 60:
        return f"{seconds} sec elapsed"
    minutes = seconds // 60
    return (
        f"{minutes // 60} hr {minutes % 60} min elapsed"
        if minutes >= 60
        else f"{minutes} min elapsed"
    )


def render(receipt: Receipt, *, files=False) -> str:
    count = len(receipt.file_changes)
    lines = [
        "FORKIT SESSION RECEIPT",
        f"{TOOL_NAMES[receipt.tool]} · {duration(receipt.elapsed_ms)}",
        "",
        f"{'At least ' if receipt.comparison == 'partial' else ''}{count} file changes",
    ]
    labels = {
        "added": "added",
        "modified": "modified",
        "removed": "removed",
        "possible_rename": "possible renames",
    }
    for kind, label in labels.items():
        total = sum(change.kind == kind for change in receipt.file_changes)
        if total:
            lines.append(f"  {total} {label}")
    if files:
        for change in receipt.file_changes:
            path = (
                f"{change.previous_path} → {change.path}" if change.previous_path else change.path
            )
            lines.append(f"  {change.kind}: {path}")
    if isinstance(receipt, ReceiptV2):
        lines.extend(render_details(receipt))
    else:
        lines.append("Legacy receipt: dependency/config details were not captured.")
    lines.extend(
        [
            "",
            "Changes observed during this session; tool reported by its hook." if receipt.tool_basis == "hook_reported" else "Changes observed during this session; tool selected by you.",
            "Scope: supported project files and declared metadata. Contents stay local."
            if isinstance(receipt, ReceiptV2)
            else "Scope: supported source and dependency files. Contents stay local.",
        ]
    )
    if receipt.comparison == "partial":
        lines.append(
            f"Partial comparison: {receipt.unknown_count} known paths could not be compared."
        )
    if receipt.status == "interrupted" or receipt.outcome == "command_failed":
        lines.append(f"Session outcome: {receipt.outcome.replace('_', ' ')}.")
    if receipt.outcome == "recovered":
        lines.append("End time unknown; changes include the interval until recovery.")
    lines.append(f"Saved locally · {receipt.session_id}")
    return "\n".join(lines)


def render_details(receipt):
    lines = []
    for category, title in (
        ("dependencies", "Dependencies"),
        ("tools", "MCP / tools"),
        ("models", "Models"),
        ("configuration", "Configuration"),
    ):
        changes = [c for c in receipt.metadata.changes if c.category == category]
        partial = receipt.metadata.status(category) == "partial"
        if changes or partial:
            lines.extend(("", f"{title} · declared metadata{' · partial' if partial else ''}"))
        for change in changes[:8]:
            value = (
                f"{change.before} → {change.after}"
                if change.kind == "changed"
                else change.after
                if change.kind == "added"
                else change.before
            )
            symbol = {"added": "+", "removed": "−", "changed": "~"}[change.kind]
            group = (
                change.key.split(":", 1)[0]
                if change.source in {"npm-manifest", "python-project"}
                else change.source
            )
            lines.append(f"  {symbol} {change.label} · {value} [{group}]")
        if len(changes) > 8:
            lines.append(f"  {len(changes) - 8} more; see private --json output.")
        if partial:
            lines.append("  Unavailable/unsupported entries are unknown, not removals.")
    passport = receipt.passport_after
    if passport.state == "consistent":
        lines.extend(
            (
                "",
                f"Agent being built: {passport.name} · {passport.version}",
                f"Passport {passport.passport_id}",
                "Core ID consistent · association declared by you",
            )
        )
        if passport.model_reference != "consistent":
            lines.append(f"Referenced model Passport: {passport.model_reference}.")
        if receipt.metadata.passport_change == "changed":
            lines.append(
                f"Selected Passport changed: {receipt.passport_before.version} → {passport.version}; lineage not inferred."
            )
    elif passport.state != "not_selected":
        lines.extend(("", f"Passport association {passport.state}: {passport.reason}."))
    count = len(receipt.meaningful_categories)
    partial = (
        receipt.comparison == "partial"
        or receipt.metadata.status() == "partial"
        or receipt.metadata.passport_change == "unknown"
    )
    lines.extend(
        (
            "",
            f"{'At least ' if partial else ''}{count} change categories"
            + (f" · {', '.join(receipt.meaningful_categories)}" if count else ""),
        )
    )
    prior, gap = receipt.since_previous, receipt.between_sessions
    if prior.comparison == "no_baseline":
        lines.append(
            "Previous comparison unavailable: receipt size limit."
            if prior.reason == "comparison_record_limit"
            else "Previous comparison: no comparable local baseline yet."
        )
    else:
        lines.append(
            f"Since comparable receipt {prior.baseline_session_id[:8]}: {'at least ' if prior.comparison == 'partial' else ''}{len(prior.file_changes)} file changes, {len(prior.metadata.changes)} metadata changes ({prior.comparison})."
        )
        lines.append(
            f"Between sessions: {'at least ' if gap.comparison == 'partial' else ''}{len(gap.file_changes)} file changes, {len(gap.metadata.changes)} metadata changes ({gap.comparison})."
        )
        if prior.skipped_sessions:
            lines.append(
                f"Skipped {prior.skipped_sessions} newer receipts without a complete comparable endpoint."
            )
        if prior.metadata.passport_change == "changed":
            lines.append("Selected Passport differs from that baseline; no lineage claim.")
    lines.append("Configured models/tools are declarations; actual runtime use is unknown.")
    return lines


def selected(args):
    return Selection(
        agent_manifest=str(args.agent_manifest.absolute()) if args.agent_manifest else None,
        registry=str(args.registry.absolute()) if args.registry else None,
        passport_id=args.passport_id,
    )


def _usage_created(store, receipt, args):
    from ..reporting.usage_capture import safely_record
    safely_record("receipt", store, receipt)
    if not args.json:
        try:
            if len(store.history(limit=2)) == 1:
                print("Optional: usage policy explains count-only participation. Reporting stays off unless you enable it.", file=sys.stderr)
        except (OSError, ValueError):
            pass


def _emit(receipt, args):
    print(
        receipt.model_dump_json(indent=2)
        if args.json
        else render(receipt, files=getattr(args, "files", False)),
        flush=True,
    )


def _run(store, args) -> int:
    if not args.argv or args.argv[0] != "--" or len(args.argv) < 2:
        raise ContractError("use_double_dash_then_explicit_command")
    argv = args.argv[1:]
    started, _snapshot = store.start(
        args.project or Path.cwd(), tool=args.tool, mode="wrapper", selection=selected(args)
    )
    if not args.json:
        print(f"Session started locally · {started.session_id}", flush=True)
    process = None
    interrupted = []
    previous_handlers = {}

    def handle(signum, _frame):
        if not interrupted:
            interrupted.extend([signum, time.monotonic()])
            if process is not None and process.poll() is None:
                process.send_signal(signum)

    outcome, code = "launch_failed", None
    try:
        for signum in (signal.SIGINT, signal.SIGTERM):
            previous_handlers[signum] = signal.signal(signum, handle)
        # Deliberate user command, with interactive streams. Arguments and output
        # are never stored; JSON mode routes command stdout to stderr directly.
        environment = os.environ.copy()
        environment["PWD"] = str((args.project or Path.cwd()).absolute())
        process = subprocess.Popen(
            argv,
            cwd=(args.project or Path.cwd()).absolute(),
            env=environment,
            stdout=sys.stderr if args.json else None,
        )
        while process.poll() is None:
            if interrupted and time.monotonic() - interrupted[1] > 5:
                process.kill()
            try:
                process.wait(timeout=0.1)
            except subprocess.TimeoutExpired:
                continue
        code = process.returncode
        outcome = (
            "interrupted"
            if interrupted or code < 0
            else "command_exited"
            if code == 0
            else "command_failed"
        )
    except OSError:
        outcome = "launch_failed"
    finally:
        for signum, old_handler in previous_handlers.items():
            signal.signal(signum, old_handler)
    receipt = store.finish(started.session_id, outcome=outcome, exit_code=code)
    _emit(receipt, args)
    _usage_created(store, receipt, args)
    if code is None:
        return 2
    return min(255, 128 - code) if code < 0 else code


def command(args) -> int:
    try:
        store = SessionStore(args.store or Path.home() / ".forkit-radar")
        if args.command in {"view", "summary", "summary-card"}:
            from ..identity.storage import write_new
            from .summary import build, text

            report = build(store, timezone_name=args.timezone, limit=getattr(args, "limit", 1), project_id=args.project_id)
            if args.command == "summary-card":
                from .summary_cards import encode, project

                card = project(report, args.period)
                if args.json:
                    print(card.model_dump_json(indent=2))
                else:
                    write_new(args.output, encode(card, args.output.suffix.lower()))
                    print("Aggregate summary card saved locally. Review before sharing. Nothing uploaded.")
            elif args.json:
                if args.command == "summary":
                    print(json.dumps({k: v for k, v in report.items() if k != "records"}, indent=2))
                else:
                    print(json.dumps(report, indent=2))
            elif args.command == "summary":
                print(text(report, args.period))
            else:
                from .private_view import render as private_view

                if args.output.suffix.lower() != ".html":
                    raise ContractError("private_view_requires_html_output")
                write_new(args.output, private_view(report))
                print("Private history view saved locally. Open the HTML file in your browser. It contains project details; use an aggregate card for public sharing. Nothing uploaded.")
        elif args.command == "storage":
            from .maintenance import backup, compact, recover, status

            if args.storage_action == "backup":
                backup(store, args.output)
                result = {"backup": "created", "privacy": "private_session_database", "published": False}
            elif args.storage_action == "compact":
                result = compact(store, keep=args.keep, apply=args.apply)
            elif args.storage_action == "recover":
                result = recover(store)
            else:
                result = status(store)
            if args.json:
                print(json.dumps(result, indent=2))
            elif args.storage_action == "backup":
                print("Private session backup saved. Contains local paths and keys; keep it private. Nothing uploaded.")
            elif args.storage_action == "compact":
                print(f"{'Compacted' if result['applied'] else 'Preview'}: {result['snapshots']} snapshots, {result['payload_bytes']} payload bytes.")
                print(f"Keep latest {args.keep} after snapshots per project. All receipts and active baselines remain.")
                print(result['comparison_effect'])
                print(result['space_effect'])
                if not args.apply:
                    print("Back up first. Run the same command with --apply to remove these snapshots.")
            elif args.storage_action == "recover":
                print("SQLite rollback/recovery check completed. Corrupt records are not repaired.")
                print(f"{result['active_sessions']} active sessions remain. Use session recover <id> if their end boundary was lost.")
            else:
                print("Local session storage: " + result['state'].replace('_', ' '))
                if result['state'] != 'not_initialized':
                    print(f"{result['receipt_count']} receipts · {result['active_sessions']} active · {result['used_bytes'] // 1024} KiB used of {result['limit_bytes'] // 1024} KiB")
                    print("Use storage backup and storage compact to retain receipts and reclaim snapshot pages. No account.")
        elif args.command == "card":
            from ..identity.storage import write_new
            from .cards import encode, project

            card = project(store.receipt(args.session_id))
            if args.json:
                print(card.model_dump_json(indent=2))
            else:
                write_new(args.output, encode(card, args.output.suffix.lower()))
                print("Aggregate card saved locally. Review it before sharing. Nothing uploaded.")
        elif args.command == "receipt":
            _emit(store.receipt(args.session_id), args)
        elif args.command == "history":
            history = store.history(limit=args.limit)
            if args.json:
                print(json.dumps([r.model_dump(mode="json") for r in history], indent=2))
            else:
                for receipt in history:
                    comparison = receipt.comparison
                    extra = ""
                    if isinstance(receipt, ReceiptV2):
                        extra = f" · {len(receipt.metadata.changes)} metadata changes · {len(receipt.meaningful_categories)} categories"
                        if (
                            receipt.metadata.status() == "partial"
                            or receipt.metadata.passport_change == "unknown"
                        ):
                            comparison = "partial"
                    print(
                        f"{receipt.session_id}  {TOOL_NAMES[receipt.tool]}  "
                        f"{'at least ' if comparison == 'partial' else ''}{len(receipt.file_changes)} file changes{extra}  "
                        f"{receipt.status} · {comparison} comparison"
                    )
                if not history:
                    print("No local receipts yet. Start with forkit-radar session --help.")
        elif args.session_action == "run":
            return _run(store, args)
        elif args.session_action == "start":
            started, snapshot = store.start(
                args.project or Path.cwd(), tool=args.tool, selection=selected(args)
            )
            if args.json:
                print(
                    json.dumps(
                        {
                            "session_id": started.session_id,
                            "tool": started.tool,
                            "tracked_files": len(snapshot.files),
                            "unknown_files": len(snapshot.unknown_paths),
                        },
                        indent=2,
                    )
                )
            else:
                print(f"Local session started · {TOOL_NAMES[started.tool]}")
                print(
                    f"Baseline: {len(snapshot.files)} supported files; {len(snapshot.unknown_paths)} unavailable."
                )
                print(
                    "Capturing supported root dependencies and project MCP/model declarations locally."
                )
                print(
                    "Finish from this project: forkit-radar stop"
                    + (" --project " + shlex.quote(str(args.project)) if args.project else "")
                    + (" --store " + shlex.quote(str(args.store)) if args.store else "")
                )
        elif args.session_action == "active":
            entries = store.active()
            data = [
                {
                    "session_id": e.started.session_id,
                    "tool": e.started.tool,
                    "started_at": e.started.started_at,
                }
                for e in entries
            ]
            print(
                json.dumps(data, indent=2)
                if args.json
                else "\n".join(f"{e['session_id']}  {TOOL_NAMES[e['tool']]}  active" for e in data)
                or "No active local sessions."
            )
        else:
            if args.session_action == "stop" and args.session_id is None:
                entry = store.active_in(args.project or Path.cwd())
                if entry is None:
                    raise ContractError("no_active_session_in_selected_project")
                if entry.started.capture_mode != "manual":
                    raise ContractError("wrapped_session_finishes_when_command_exits")
                args.session_id = entry.started.session_id
            receipt = store.finish(
                args.session_id,
                outcome="recovered" if args.session_action == "recover" else "manual_stop",
            )
            _emit(receipt, args)
            _usage_created(store, receipt, args)
        return 0
    except ContractError as exc:
        print(f"Session operation unavailable: {exc}.", file=sys.stderr)
        if str(exc) in {"store_capacity_exhausted", "session_capacity_low_backup_or_compact"}:
            print("History remains local. Use storage status, create a private storage backup, then preview storage compact. Pass the same --store path.", file=sys.stderr)
        elif str(exc) == "store_unavailable_or_invalid":
            print("If a writer was interrupted, try storage recover with the same --store. This cannot repair corrupted history.", file=sys.stderr)
        return 2
    except (OSError, ValueError, TypeError):
        print(
            "Session operation unavailable: invalid input or inaccessible local storage/project.",
            file=sys.stderr,
        )
        return 2
