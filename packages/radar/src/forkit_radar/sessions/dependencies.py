"""Bounded declared dependencies, never resolution, installation or script execution."""

from __future__ import annotations

import hashlib
import hmac
import re
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

from ..discovery.metadata import load_metadata
from ..discovery.safeio import read_metadata
from ..jsonio import ContractError, load_json
from .details import Fact, Source

GROUPS = ("dependencies", "devDependencies", "optionalDependencies", "peerDependencies")
NPM_NAME = re.compile(r"(?:@[a-z0-9][a-z0-9._-]*/)?[a-z0-9][a-z0-9._-]*")
RANGE = re.compile(
    r"[~^<>=]{0,2}v?(?:[0-9]+|[xX*])(?:\.(?:[0-9]+|[xX*])){0,2}(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?"
)
VERSION = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?")
UNSUPPORTED = (
    "pnpm-lock.yaml",
    "yarn.lock",
    "bun.lock",
    "bun.lockb",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
    "Cargo.lock",
    "Cargo.toml",
    "go.mod",
    "Gemfile.lock",
    "Gemfile",
    "composer.lock",
    "composer.json",
    "Pipfile",
    "setup.py",
    "setup.cfg",
)


def token(key: bytes, domain: str, value: str) -> str:
    return hmac.new(key, (domain + "\n" + value).encode(), hashlib.sha256).hexdigest()


def npm_name(value):
    if not isinstance(value, str) or len(value) > 128 or not NPM_NAME.fullmatch(value):
        raise ValueError("unsupported_package_name")
    return value


def npm_range(value):
    # Deliberately conservative: URLs, local paths, aliases and arbitrary tags
    # can contain private data. No URLs, credentials or unsupported raw specs.
    if not isinstance(value, str):
        raise ValueError("unsupported_dependency_spec")
    value = " ".join(value.split())
    if value not in {"*", "latest", "next", "beta", "canary"}:
        if len(value) > 128:
            raise ValueError("unsupported_dependency_spec")
        for branch in value.split("||"):
            parts = re.sub(r"([~^<>=]+)\s+", r"\1", branch).split()
            if len(parts) == 3 and parts[1] == "-":
                parts = [parts[0], parts[2]]
            if not parts or any(not RANGE.fullmatch(part) for part in parts):
                raise ValueError("unsupported_dependency_spec")
    return value


def manifest(data):
    facts, partial = [], bool(data.get("workspaces"))
    for group in GROUPS:
        entries = data.get(group, {})
        if not isinstance(entries, dict):
            partial = True
            continue
        for name, spec in entries.items():
            if len(facts) >= 512:
                return facts, True
            try:
                name = npm_name(name)
                facts.append(Fact(key=f"{group}:{name}", label=name, value=npm_range(spec)))
            except ValueError:
                partial = True
    return facts, partial


def lock(data):
    if type(data.get("lockfileVersion")) is not int or data["lockfileVersion"] not in {2, 3}:
        raise ValueError("unsupported_lock_version")
    entries = data.get("packages")
    if not isinstance(entries, dict):
        raise ValueError("invalid_lock")
    facts, partial = [], False
    for location, entry in entries.items():
        if location == "":
            continue
        if len(facts) >= 512:
            return facts, True
        try:
            if not isinstance(entry, dict) or entry.get("link") is True:
                raise ValueError
            # Stable install slots disambiguate nested copies of a dependency.
            parts = location.split("node_modules/")
            if parts[0] != "" or len(location) > 240 or len(parts) > 8:
                raise ValueError
            for parent in parts[1:-1]:
                npm_name(parent.removesuffix("/"))
            name = npm_name(parts[-1])
            version = entry.get("version")
            if not isinstance(version, str) or len(version) > 128 or not VERSION.fullmatch(version):
                raise ValueError
            # Aliased registry packages have an explicit real package name.
            actual = npm_name(entry.get("name", name))
            value = version if actual == name else f"{actual}@{version}"
            facts.append(Fact(key=location, label=name, value=value))
        except (ValueError, TypeError, AttributeError):
            partial = True
    return facts, partial


def python_requirement(raw, group, key):
    if not isinstance(raw, str) or len(raw) > 2048:
        raise ValueError
    requirement = Requirement(raw)
    if requirement.url or any(s.operator == "===" for s in requirement.specifier):
        raise ValueError("direct_references_out_of_scope")
    name = canonicalize_name(requirement.name)
    extras = ",".join(sorted(canonicalize_name(e) for e in requirement.extras))
    label = f"{name}[{extras}]" if extras else name
    value = str(requirement.specifier) or "*"
    marker = (
        token(key, "forkit-session-marker-v1", str(requirement.marker))
        if requirement.marker
        else "unconditional"
    )
    # Conditions are compared, not evaluated against this machine. Arbitrary
    # marker literals stay out of stored data and terminal output.
    if requirement.marker:
        value += " (conditional)"
    return Fact(key=f"{group}:{label}:{marker}", label=label, value=value)


def pyproject(data, key):
    project = data.get("project")
    if project is None:
        # setup.py, backend-generated and Poetry metadata are not empty deps.
        return [], True
    if not isinstance(project, dict):
        raise ValueError
    dynamic = project.get("dynamic", [])
    if not isinstance(dynamic, list):
        raise ValueError
    partial = bool({"dependencies", "optional-dependencies"} & set(dynamic))
    groups = {"dependencies": project.get("dependencies", [])}
    optional = project.get("optional-dependencies", {})
    if not isinstance(optional, dict):
        partial = True
    else:
        for group, entries in optional.items():
            if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}", group):
                partial = True
            else:
                normalized = f"optional-{canonicalize_name(group)}"
                if normalized in groups:
                    raise ContractError("duplicate_dependency_group")
                groups[normalized] = entries
    facts = {}
    for group, entries in groups.items():
        if not isinstance(entries, list):
            partial = True
            continue
        for raw in entries:
            if len(facts) >= 512:
                return list(facts.values()), True
            try:
                fact = python_requirement(raw, group, key)
                if fact.key in facts:
                    # Multiple constraints for the same key require a resolver;
                    # suppress the source instead of choosing an arbitrary one.
                    raise ContractError("duplicate_dependency")
                facts[fact.key] = fact
            except ContractError:
                raise
            except ValueError:
                partial = True
    return list(facts.values()), partial


def requirements(raw, key):
    facts, partial = {}, False
    for line in raw.decode("utf-8").splitlines():
        line = re.split(r"\s+#", line, maxsplit=1)[0].strip()
        if not line or line.startswith("#"):
            continue
        if len(facts) >= 512:
            return list(facts.values()), True
        try:
            # A scoped subset of pip's file syntax: one PEP 508 requirement per
            # line. Never follow includes, expand env vars or read indexes.
            fact = python_requirement(line, "requirements", key)
            if fact.key in facts:
                raise ContractError("duplicate_dependency")
            facts[fact.key] = fact
        except ContractError:
            raise
        except ValueError:
            partial = True
    return list(facts.values()), partial


def capture(project: Path, key: bytes):
    readers = (
        (
            "npm-manifest",
            "package.json",
            lambda p: manifest(load_json(read_metadata(p, limit=1_048_576))),
        ),
        (
            "npm-lock",
            "package-lock.json",
            lambda p: lock(load_json(read_metadata(p, limit=1_048_576))),
        ),
        (
            "npm-shrinkwrap",
            "npm-shrinkwrap.json",
            lambda p: lock(load_json(read_metadata(p, limit=1_048_576))),
        ),
        ("python-project", "pyproject.toml", lambda p: pyproject(load_metadata(p, toml=True), key)),
        ("python-requirements", "requirements.txt", lambda p: requirements(read_metadata(p), key)),
    )
    for source, filename, reader in readers:
        try:
            facts, partial = reader(project / filename)
            yield Source(
                key=source,
                category="dependencies",
                state="partial" if partial else "complete",
                reason="unsupported_entries" if partial else "declared_dependencies_only",
                facts=sorted(facts, key=lambda f: f.key),
            )
        except FileNotFoundError:
            yield Source(key=source, category="dependencies", state="absent", reason="not_found")
        except (OSError, ValueError, TypeError, RecursionError):
            yield Source(
                key=source,
                category="dependencies",
                state="unavailable",
                reason="unreadable_or_unsupported_metadata",
            )
    # Only stat fixed unsupported filenames; never parse a binary lock or follow
    # its referenced files. Absence is not a claim about every package manager.
    state, reason = "absent", "no_known_unsupported_root_manifest"
    try:
        for filename in UNSUPPORTED:
            try:
                (project / filename).lstat()
            except FileNotFoundError:
                continue
            state, reason = "unsupported", "unsupported_root_dependency_format_present"
            break
    except OSError:
        state, reason = "unavailable", "unsupported_format_check_unavailable"
    yield Source(key="other-dependencies", category="dependencies", state=state, reason=reason)
