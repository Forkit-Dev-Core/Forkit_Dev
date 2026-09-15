"""Read-only first-use guidance. No tool launch, source scan, account or network."""
from __future__ import annotations

import json
import platform
import re
import shutil
import sys
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from . import __version__
from .sessions.inventory import select_project
from .sessions.maintenance import status
from .sessions.models import TOOL_NAMES
from .sessions.storage import SessionStore


def welcome():
    return """FORKIT SESSION RECEIPT
You vibe code. Forkit remembers what changed.

Install once. Setup configures detected coding tools across local Git projects.
  forkit-radar setup
  # Restart Codex and review Forkit in /hooks once; then code as usual.
  forkit-radar open
  forkit-radar receipt
  forkit-radar history
  forkit-radar card --output receipt.html

Wrapper fallback: forkit-radar session run --tool codex -- codex
Manual fallback: forkit-radar start --tool cursor, then forkit-radar stop
Claude Code / Cursor hook adapters are experimental.
Choose claude-code, cursor, codex or other with --tool.
Use the same command path and --store, if selected, for every step.
Pause automatic capture: forkit-radar setup --disable
Local receipts need no Forkit account. Reporting is off until explicit consent.
Tool selection describes your session; AI authorship is unverified.
Signed identity continuity is not implemented yet. Full commands: --help"""


def configure(commands):
    p = commands.add_parser("doctor", help="Check local first-use prerequisites without changing anything")
    p.add_argument("--project", type=Path, help="Selected Git root; defaults to current directory")
    p.add_argument("--store", type=Path)
    p.add_argument("--tool", choices=tuple(TOOL_NAMES), default="other")
    p.add_argument("--json", action="store_true", help="Fixed diagnostic fields only; no paths or credentials")


def diagnose(project, root, tool="other"):
    checks = []

    def add(name, state, action):
        checks.append(dict(check=name, state=state, action=action))

    add("python", "ready" if (3, 10) <= sys.version_info[:2] <= (3, 13) else "unvalidated", "Use Python 3.10–3.13; an offline kit needs its exact minor version.")
    machine = platform.machine().lower()
    add("platform", "ready" if sys.platform in {"darwin", "linux"} and machine in {"arm64", "aarch64", "x86_64", "amd64"} else "unvalidated", "Use the bundle matching your operating system, architecture and Python minor version. Release checks cover macOS Apple silicon and Linux x86_64.")
    try:
        core = version("forkit-core")
    except PackageNotFoundError:
        core = None
    add("core", "ready" if core == "0.1.0" else "blocked", "Install Core and Radar together from the supplied kit.")
    try:
        selected, _ = select_project(project)
        add("git_project", "ready", "The selected directory is a Git root. No source contents were scanned.")
    except (ValueError, OSError):
        selected = None
        add("git_project", "blocked", "Install Git, open the root of your Git project, then run doctor again. Do not initialize an unrelated parent directory.")
    store = SessionStore(root)
    if selected and (store.root == selected or selected in store.root.parents):
        add("storage", "blocked", "Choose a private --store outside the captured project.")
    else:
        try:
            storage = status(store)
            add("storage", "blocked" if storage["state"] == "near_capacity" else "ready", "Back up and review storage compact if near capacity. A new store is created only when you start a session.")
        except (OSError, ValueError):
            add("storage", "blocked", "Check store permissions or use storage recover after an interrupted writer. Existing history is not repaired automatically.")
    executable = {"codex": "codex", "claude-code": "claude", "cursor": "cursor"}.get(tool)
    if executable:
        found = shutil.which(executable) is not None
        add("selected_tool_command", "ready" if found else "optional", "Command found on PATH; it was not run." if found else "Not on PATH. GUI editors still work with start/stop; a CLI wrapper needs its command installed.")
    return {"schema_version": "1.0", "kind": "forkit_local_doctor", "radar_version": __version__,
            "python": ".".join(map(str, sys.version_info[:3])),
            "core_version": core if core and re.fullmatch(r"[A-Za-z0-9.+-]{1,40}", core) else None,
            "ready": all(c["state"] != "blocked" for c in checks), "checks": checks,
            "account_required": False, "network_used": False, "writes_performed": False}


def doctor_command(args):
    try:
        result = diagnose(args.project or Path.cwd(), args.store or Path.home() / ".forkit-radar", args.tool)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print("Forkit local setup: " + ("ready" if result["ready"] else "needs attention"))
            for check in result["checks"]:
                print(f"{check['check']}: {check['state']} — {check['action']}")
            print("Nothing changed or uploaded. Next: forkit-radar setup --status, then forkit-radar open")
        return 0 if result["ready"] else 1
    except (ValueError, OSError):
        print("Local setup could not be checked. Select an accessible Git root and private store.", file=sys.stderr)
        return 2
