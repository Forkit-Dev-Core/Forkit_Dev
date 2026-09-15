"""Opt-in project snapshots: Git lists paths; Radar reads bounded source files.

No source bodies, Git patches, blob IDs, command output or repository config are
persisted. These content reads belong to explicit session mode, never scan.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import selectors
import stat
import subprocess
import time
from pathlib import Path

from ..discovery.safeio import directory, read_at
from ..jsonio import ContractError
from .models import MAX_FILES, FileChange, FileState, Snapshot, safe_relative

GIT = "/usr/bin/git"
MAX_GIT_BYTES = 1_048_576
MAX_FILE_BYTES = 4_194_304
MAX_TOTAL_BYTES = 67_108_864
MAX_CAPTURE_SECONDS = 15
SOURCE_SUFFIXES = frozenset(
    {
        ".py",
        ".pyi",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rs",
        ".java",
        ".c",
        ".h",
        ".cc",
        ".cpp",
        ".hpp",
        ".cs",
        ".rb",
        ".php",
        ".swift",
        ".kt",
        ".kts",
        ".scala",
        ".vue",
        ".svelte",
        ".css",
        ".scss",
        ".sass",
        ".less",
        ".html",
        ".htm",
        ".sql",
        ".sh",
        ".bash",
        ".zsh",
        ".fish",
        ".lua",
        ".r",
        ".dart",
        ".ex",
        ".exs",
        ".elm",
        ".clj",
        ".cljs",
        ".proto",
        ".graphql",
        ".gql",
    }
)
MANIFEST_NAMES = frozenset(
    {
        "package.json",
        "package-lock.json",
        "npm-shrinkwrap.json",
        "yarn.lock",
        "pnpm-lock.yaml",
        "pyproject.toml",
        "poetry.lock",
        "uv.lock",
        "requirements.txt",
        "cargo.toml",
        "cargo.lock",
        "go.mod",
        "go.sum",
        "gemfile",
        "gemfile.lock",
        "composer.json",
        "composer.lock",
    }
)
EXCLUDED_DIRECTORIES = frozenset(
    {
        ".git",
        ".hg",
        ".svn",
        ".forkit-radar",
        ".claude",
        ".codex",
        ".cursor",
        ".vscode",
        ".idea",
        ".ssh",
        ".aws",
        ".azure",
        ".config",
        "node_modules",
        ".venv",
        "venv",
        "__pycache__",
        "dist",
        "build",
        ".next",
        ".cache",
        "vendor",
        "coverage",
    }
)


def allowed(path: str) -> bool:
    parts = Path(path).parts
    lower = tuple(p.lower() for p in parts)
    if any(
        p in EXCLUDED_DIRECTORIES or p.startswith((".env", "secret", "credential"))
        for p in lower[:-1]
    ):
        return False
    name = lower[-1]
    if (
        name.startswith((".env", "secret", "credential", "token", "id_rsa", "id_ed25519"))
        or name.endswith((".pem", ".key", ".p12", ".pfx", ".keystore"))
        or name in {"claude.md", "agents.md", "gemini.md"}
    ):
        return False
    return Path(name).suffix in SOURCE_SUFFIXES or name in MANIFEST_NAMES


def git(project: Path, *arguments: str) -> bytes:
    """Two fixed read-only Git operations; no shell, filters, hooks or fetches."""
    if arguments not in {
        ("rev-parse", "--show-prefix"),
        ("ls-files", "-z", "--cached", "--others", "--exclude-standard", "--"),
    }:
        raise ContractError("unsupported_session_git_operation")
    env = {
        "PATH": "/usr/bin:/bin",
        "LC_ALL": "C",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_SYSTEM": "/dev/null",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "GIT_NO_LAZY_FETCH": "1",
    }
    command = [
        GIT,
        "--no-optional-locks",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.untrackedCache=false",
        "-c",
        "core.hooksPath=/dev/null",
        *arguments,
    ]
    try:
        process = subprocess.Popen(
            command,
            cwd=project,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        raise ContractError("git_unavailable") from None
    payload = bytearray()
    deadline = time.monotonic() + 5
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ)
            while selector.get_map():
                if time.monotonic() >= deadline:
                    raise ContractError("git_inventory_timeout")
                for _, _events in selector.select(min(0.1, max(0, deadline - time.monotonic()))):
                    chunk = os.read(process.stdout.fileno(), 65_536)
                    if not chunk:
                        selector.unregister(process.stdout)
                        break
                    payload.extend(chunk)
                    if len(payload) > MAX_GIT_BYTES:
                        raise ContractError("git_inventory_limit")
        if process.wait(timeout=max(0.01, deadline - time.monotonic())) != 0:
            raise ContractError("git_repository_unavailable")
        return bytes(payload)
    except subprocess.TimeoutExpired:
        raise ContractError("git_inventory_timeout") from None
    finally:
        if process.poll() is None:
            process.kill()
        process.wait(timeout=2)
        process.stdout.close()


def select_project(path: Path) -> tuple[Path, tuple[int, int]]:
    project = path.absolute()
    if project == Path(project.anchor) or project == Path.home():
        raise ContractError("select_a_project_not_home")
    with directory(project) as descriptor:
        info = os.fstat(descriptor)
        identity = (info.st_dev, info.st_ino)
    if git(project, "rev-parse", "--show-prefix").strip():
        raise ContractError("select_git_project_root")
    return project, identity


def capture(project: Path, key: bytes, *, previous: Snapshot | None = None) -> Snapshot:
    files, unknown, reasons = [], set(), set()
    excluded, total_bytes = 0, 0
    complete = True
    start = time.monotonic()
    try:
        raw = git(project, "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--")
        if raw and not raw.endswith(b"\0"):
            raise ContractError("invalid_git_inventory")
    except ContractError:
        return Snapshot(
            files=(),
            unknown_paths=(),
            excluded_count=0,
            inventory_complete=False,
            reasons=("inventory_unavailable",),
        )
    paths = set()
    for item in raw.split(b"\0"):
        if not item:
            continue
        try:
            path = safe_relative(item.decode("utf-8", errors="strict"))
        except (ValueError, UnicodeError):
            complete = False
            reasons.add("unsupported_filename")
            continue
        if not allowed(path):
            excluded += 1
            continue
        paths.add(path)
    old_paths = {f.path for f in previous.files} if previous else set()
    for index, path in enumerate(sorted(paths)):
        if index >= MAX_FILES or time.monotonic() - start >= MAX_CAPTURE_SECONDS:
            complete = False
            reasons.add("capture_limit")
            break
        target = project / path
        try:
            with directory(target.parent) as parent:
                before = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
                if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1:
                    raise ValueError("unsupported_file")
                if (
                    before.st_size > MAX_FILE_BYTES
                    or total_bytes + before.st_size > MAX_TOTAL_BYTES
                ):
                    raise ValueError("capture_limit")
                content = read_at(parent, target.name, MAX_FILE_BYTES)
                after = os.stat(target.name, dir_fd=parent, follow_symlinks=False)
                if any(
                    getattr(before, f) != getattr(after, f)
                    for f in (
                        "st_dev",
                        "st_ino",
                        "st_ctime_ns",
                        "st_mtime_ns",
                        "st_size",
                        "st_mode",
                    )
                ):
                    raise ValueError("file_changed_during_capture")
            total_bytes += len(content)
            files.append(
                FileState(
                    path=path,
                    fingerprint=hmac.new(
                        key, b"forkit-session-file-v1\n" + content, hashlib.sha256
                    ).hexdigest(),
                    executable=bool(before.st_mode & 0o111),
                )
            )
        except FileNotFoundError:
            # Tracked deletions remain in ls-files. Absence is a valid endpoint.
            continue
        except (OSError, ValueError):
            unknown.add(path)
            reasons.add("file_unavailable_or_outside_limits")
    # An untracked file may disappear from Git's list after ignore rules change.
    # It is not a deletion if it still exists or cannot safely be checked.
    for path in sorted(old_paths - paths):
        target = project / path
        try:
            with directory(target.parent) as parent:
                os.stat(target.name, dir_fd=parent, follow_symlinks=False)
            unknown.add(path)
            reasons.add("previous_file_outside_inventory")
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            unknown.add(path)
            reasons.add("previous_file_unavailable")
    return Snapshot(
        files=tuple(files),
        unknown_paths=tuple(sorted(unknown)),
        excluded_count=excluded,
        inventory_complete=complete,
        reasons=tuple(sorted(reasons)),
    )


def difference(before: Snapshot, after: Snapshot) -> tuple[tuple[FileChange, ...], int, bool]:
    left, right = {f.path: f for f in before.files}, {f.path: f for f in after.files}
    unknown = set(before.unknown_paths) | set(after.unknown_paths)
    additions, removals, changes = {}, {}, []
    complete_inventory = before.inventory_complete and after.inventory_complete
    for path in sorted(left.keys() | right.keys()):
        if path in unknown:
            continue
        a, b = left.get(path), right.get(path)
        if a is not None and b is not None:
            if (a.fingerprint, a.executable) != (b.fingerprint, b.executable):
                changes.append(FileChange(kind="modified", path=path))
        elif not complete_inventory:
            unknown.add(path)
        elif b is None:
            removals[path] = a
        else:
            additions[path] = b
    # Exact unique content matches suggest a rename; they cannot prove one.
    for old_path, old in tuple(removals.items()):
        matching_new = [
            p
            for p, f in additions.items()
            if (f.fingerprint, f.executable) == (old.fingerprint, old.executable)
        ]
        matching_old = [
            p
            for p, f in removals.items()
            if (f.fingerprint, f.executable) == (old.fingerprint, old.executable)
        ]
        if len(matching_new) == len(matching_old) == 1:
            new_path = matching_new[0]
            changes.append(
                FileChange(kind="possible_rename", path=new_path, previous_path=old_path)
            )
            del removals[old_path]
            del additions[new_path]
    changes.extend(FileChange(kind="removed", path=p) for p in removals)
    changes.extend(FileChange(kind="added", path=p) for p in additions)
    return (
        tuple(sorted(changes, key=lambda c: (c.path, c.kind))),
        len(unknown),
        complete_inventory and not unknown,
    )
