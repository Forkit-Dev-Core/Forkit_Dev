"""Contract commands and passive, unsaved development scans."""

from __future__ import annotations

import argparse
import json
import os
import stat
import sys
from pathlib import Path

from . import __version__


class _Parser(argparse.ArgumentParser):
    def error(self, _message: str) -> None:
        self.exit(2, "Invalid command arguments. Run forkit-radar --help.\n")


def main(argv: list[str] | None = None) -> int:
    parser = _Parser(
        prog="forkit-radar",
        description="Local Session Receipt, passive discovery and Core Passport tools. No Forkit account needed. Signed identity continuity is not implemented yet.",
    )
    parser.add_argument("--version", action="version", version=f"forkit-radar {__version__}")
    commands = parser.add_subparsers(dest="command")
    from .sessions.cli import configure as configure_sessions

    configure_sessions(commands)
    from .capture.cli import configure as configure_hooks
    configure_hooks(commands)
    from .reporting.cli import configure as configure_reporting

    configure_reporting(commands)
    from .reporting.usage_cli import configure as configure_usage
    configure_usage(commands)
    from .onboarding import configure as configure_onboarding

    configure_onboarding(commands)
    schema = commands.add_parser("schema", help="Print a versioned JSON shape schema")
    schema.add_argument("contract")
    validate = commands.add_parser(
        "validate", help="Validate a local document's structure, not authenticity"
    )
    validate.add_argument("contract")
    validate.add_argument("path")
    scan_parser = commands.add_parser("scan", help="Inspect supported product metadata locally")
    scan_parser.add_argument(
        "--no-save",
        action="store_true",
        required=True,
        help="Required during development until transactional storage is implemented",
    )
    scan_parser.add_argument(
        "--json", action="store_true", help="Private diagnostic JSON to stdout"
    )
    scan_parser.add_argument(
        "--source",
        choices=("all", "applications", "processes", "mcp", "models", "agents"),
        default="all",
    )
    scan_parser.add_argument(
        "--project", type=Path, help="Explicit project for MCP and LangGraph metadata only"
    )
    scan_parser.add_argument(
        "--models-root", type=Path, help="Explicit Ollama models directory; blobs are never read"
    )
    scan_parser.add_argument(
        "--agent-manifest",
        type=Path,
        help="Explicit Radar agent metadata document; contents remain declarations",
    )
    scan_parser.add_argument(
        "--registry", type=Path, help="Explicit read-only Core registry for declared references"
    )
    scan_parser.add_argument("--metrics-store", type=Path, help="Optional aggregate journal; writes counts only if reporting was explicitly enabled")
    passport = commands.add_parser(
        "passport", help="Check or explicitly create Core Passport documents"
    )
    passport_commands = passport.add_subparsers(dest="passport_command", required=True)
    inspect = passport_commands.add_parser(
        "inspect", help="Raw ID and schema consistency, not authenticity"
    )
    inspect_source = inspect.add_mutually_exclusive_group(required=True)
    inspect_source.add_argument("--file", type=Path)
    inspect_source.add_argument("--passport-id")
    inspect.add_argument("--kind", choices=("agent", "model"))
    inspect.add_argument("--registry", type=Path)
    inspect.add_argument("--json", action="store_true")
    create = passport_commands.add_parser(
        "create", help="Preview required metadata; --output explicitly creates a new file"
    )
    create.add_argument("--input", type=Path, required=True)
    create.add_argument("--output", type=Path)
    create.add_argument(
        "--model-passport",
        type=Path,
        help="Required checked ModelPassport document for agent creation",
    )
    create.add_argument("--json", action="store_true")
    create.add_argument("--metrics-store", type=Path, help="Optional aggregate journal; requires prior reporting consent")
    enroll = commands.add_parser(
        "enroll",
        help="Preview explicit agent selection; optionally save an unsigned pending proposal",
    )
    source = enroll.add_mutually_exclusive_group(required=True)
    source.add_argument("--agent-manifest", type=Path)
    source.add_argument("--project", type=Path)
    enroll.add_argument("--graph-key")
    enroll.add_argument("--registry", type=Path)
    enroll.add_argument("--passport-id", action="append", default=[])
    enroll.add_argument("--store", type=Path)
    enroll.add_argument("--save-pending", action="store_true")
    enroll.add_argument(
        "--json", action="store_true", help="Private diagnostic; no source locators"
    )
    enrollment = commands.add_parser("enrollment", help="Inspect or cancel saved pending proposals")
    operations = enrollment.add_subparsers(dest="enrollment_command", required=True)
    for action in ("list", "inspect", "cancel"):
        operation = operations.add_parser(action)
        if action != "list":
            operation.add_argument("proposal_id")
        operation.add_argument("--store", type=Path)
        operation.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    if args.command is None:
        from .onboarding import welcome

        print(welcome())
        return 0
    if args.command == "hooks":
        from .capture.cli import command as hooks_command
        return hooks_command(args)
    if args.command == "doctor":
        from .onboarding import doctor_command

        return doctor_command(args)
    if args.command == "metrics":
        from .reporting.cli import command as reporting_command

        return reporting_command(args)
    if args.command == "usage":
        from .reporting.usage_cli import command as usage_command
        return usage_command(args)
    if args.command in {"session", "receipt", "history", "card", "storage", "view", "summary", "summary-card"}:
        from .sessions.cli import command as session_command

        return session_command(args)
    if args.command in {"passport", "enroll", "enrollment"}:
        return _identity_command(args)
    if args.command == "scan":
        from .discovery.scan import scan

        selection = {
            "all": None,
            "applications": ("applications",),
            "processes": ("processes",),
            "mcp": ("codex-mcp", "cursor-mcp"),
            "models": ("ollama",),
            "agents": (("langgraph",) if args.project else ())
            + (("agent-manifest",) if args.agent_manifest else ()),
        }[args.source]
        try:
            report = scan(
                selection,
                project=args.project,
                models_root=args.models_root,
                agent_file=args.agent_manifest,
                registry=args.registry,
            )
        except ValueError:
            print("Invalid source selection. See forkit-radar scan --help.", file=sys.stderr)
            return 2
        if args.json:
            print(report.model_dump_json(indent=2))
        else:
            print(
                "Supported product candidates. No agent identity or runtime authentication checked."
            )
            for source in report.sources:
                print(f"{source.scope}: {source.status} ({source.reason})")
                for finding in source.findings:
                    if finding.observation.manifest is None:
                        continue
                    if finding.detail:
                        detail = finding.detail
                        label = {
                            "codex-mcp": "Codex MCP declaration",
                            "cursor-mcp": "Cursor MCP declaration",
                            "ollama": "Ollama model metadata",
                            "langgraph": "LangGraph agent declaration",
                            "agent-manifest": "Selected agent declaration",
                        }[detail.adapter]
                        print(f"  {label} {detail.entry_index} — {detail.precedence}")
                        if detail.transport is not None:
                            print(
                                f"    transport: {detail.transport}; configured activation: {detail.activation}"
                            )
                    else:
                        print(
                            f"  {finding.observation.manifest.declared_identity.name.value} — candidate"
                        )
                if source.unknown_entries:
                    print(f"  {source.unknown_entries} unrecognized or unprocessed entries")
                for finding in source.findings:
                    if finding.association is not None:
                        print(
                            f"  association: {finding.association.state}; Passport: {finding.evidence.passport}"
                        )
            print(
                f"{report.candidate_count} candidate observations; installations and processes are separate."
            )
            print("Not saved. Continuity/removals and Passport coverage have not been evaluated.")
        from .reporting.storage import safely_note

        safely_note("scan", report, root=args.metrics_store)
        from .reporting.usage_capture import safely_record
        safely_record("scan", report)
        return 0 if all(s.status in {"complete", "missing"} for s in report.sources) else 1

    from .contracts import CONTRACTS, read_contract
    from .jsonio import MAX_DOCUMENT_BYTES, ContractError

    try:
        if args.contract not in CONTRACTS:
            raise ContractError("unsupported_contract")
        if args.command == "schema":
            print(json.dumps(CONTRACTS[args.contract].model_json_schema(by_alias=True), indent=2))
            return 0
        # Explicit input only. Never block on FIFOs or follow a final symlink.
        flags = os.O_RDONLY | os.O_NONBLOCK | os.O_NOFOLLOW
        descriptor = os.open(args.path, flags)
        with os.fdopen(descriptor, "rb") as source:
            if not stat.S_ISREG(os.fstat(source.fileno()).st_mode):
                raise ContractError("regular_file_required")
            raw = source.read(MAX_DOCUMENT_BYTES + 1)
        read_contract(args.contract, raw)
        print("Structure valid. Authority and authenticity have not been verified.")
        return 0
    except ContractError as exc:
        print(f"Invalid document: {exc}", file=sys.stderr)
        return 2
    except OSError:
        print("Cannot read the selected document.", file=sys.stderr)
        return 2


def _identity_command(args) -> int:
    from .discovery.safeio import read_metadata
    from .identity.enrollment import preview, select_source
    from .identity.passports import check_bytes, check_file, create_bytes, lookup
    from .identity.storage import EnrollmentStore, write_new

    try:
        if args.command == "passport":
            if args.passport_command == "inspect":
                if args.file is not None:
                    result = check_file(args.file, expected_kind=args.kind)
                else:
                    if args.registry is None or args.kind is None:
                        raise ValueError
                    result = lookup(args.registry, args.passport_id, args.kind)
                print(
                    result.model_dump_json(indent=2)
                    if args.json
                    else f"Passport: {result.status} ({result.reason}). This does not authenticate an agent."
                )
                return 0 if result.status == "consistent" else 1
            raw = create_bytes(
                read_metadata(args.input.absolute()),
                model_passport=read_metadata(args.model_passport.absolute())
                if args.model_passport
                else None,
            )
            result = check_bytes(raw)
            if args.output is not None:
                write_new(args.output, raw)
                from .reporting.storage import safely_note

                safely_note("passport", result.passport_id, root=args.metrics_store)
                from .reporting.usage_capture import safely_record
                safely_record("passport", result.passport_id)
            print(
                result.model_dump_json(indent=2)
                if args.json
                else f"Core Passport {result.passport_id}: {'created in selected file' if args.output else 'preview only; no file written'}. No enrollment or authentication."
            )
            return 0
        if args.command == "enroll":
            locator, manifest = select_source(
                agent_file=args.agent_manifest, project=args.project, graph_key=args.graph_key
            )
            result = preview(manifest, registry=args.registry, passport_ids=args.passport_id)
            if args.save_pending:
                entry = EnrollmentStore(args.store or Path.home() / ".forkit-radar").propose(
                    locator, result
                )
                print(
                    entry.model_dump_json(indent=2)
                    if args.json
                    else f"Pending proposal {entry.draft.proposal_id}; reserved logical-agent ID {entry.draft.reserved_logical_agent_id}. Unsigned and unaccepted."
                )
            else:
                print(
                    result.model_dump_json(indent=2)
                    if args.json
                    else f"Enrollment preview: {locator.adapter}; association {result.association.state}; authority unavailable. Nothing saved."
                )
            if not args.json:
                print(
                    "Candidate Passport: "
                    + (result.association.selected_passport_id or "unresolved")
                )
                print(
                    "Scope: "
                    + result.manifest.scope_profile.profile_id
                    + "; "
                    + ", ".join(result.manifest.scope_profile.dimensions)
                )
                print(
                    "Core ID/schema: "
                    + (
                        result.association.candidates[0].status
                        if len(result.association.candidates) == 1
                        else "not checked"
                    )
                    + "; model reference: "
                    + result.association.model_reference
                )
                print("Pending prerequisites: " + ", ".join(result.blockers))
                print(
                    "Source binding cannot establish continuity until authority and signing checks are implemented."
                )
            return 1 if result.association.state in {"conflicted", "ambiguous"} else 0
        store = EnrollmentStore(args.store or Path.home() / ".forkit-radar")
        entries = (
            store.list()
            if args.enrollment_command == "list"
            else (
                store.cancel(args.proposal_id)
                if args.enrollment_command == "cancel"
                else store.get(args.proposal_id),
            )
        )
        if args.json:
            print(json.dumps([entry.model_dump(mode="json") for entry in entries], indent=2))
        else:
            for entry in entries:
                print(
                    f"{entry.draft.proposal_id}: {entry.state}; reserved logical-agent ID {entry.draft.reserved_logical_agent_id}"
                )
            print(f"{len(entries)} proposals. No accepted enrollment or authenticated runtime.")
        return 0
    except (ValueError, TypeError, OSError):
        # Pydantic/Core/filesystem errors can embed private input or paths.
        print(
            "Cannot complete identity operation: invalid input, unresolved association, duplicate proposal, or unavailable private storage. No accepted enrollment was created.",
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
