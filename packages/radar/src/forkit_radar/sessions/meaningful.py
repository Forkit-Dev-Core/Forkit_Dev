"""Deterministic counting policy, not a model's judgment of importance.

One dependency package/component per interval; supporting declarations are kept
together. Explained manifest files are not counted a second time. Intervals,
projects, components and actual Passport versions are never merged by name.
"""

from __future__ import annotations

from ..contracts import Contract, Counter
from .details import Delta

POLICY = "session-meaningful-changes-v1"
SOURCE_FILES = {
    "npm-manifest": "package.json", "npm-lock": "package-lock.json",
    "npm-shrinkwrap": "npm-shrinkwrap.json", "python-project": "pyproject.toml",
    "python-requirements": "requirements.txt", "codex-project-mcp": ".codex/config.toml",
    "cursor-project-mcp": ".cursor/mcp.json", "claude-project-mcp": ".mcp.json",
    "codex-project-model": ".codex/config.toml", "claude-project-model": ".claude/settings.json",
}
CATEGORIES = ("files", "dependencies", "tools", "models", "configuration", "passport")


class ChangeCounts(Contract):
    files: Counter
    dependencies: Counter
    tools: Counter
    models: Counter
    configuration: Counter
    passport: Counter


def changes(files, delta: Delta | None, before_passport=None, after_passport=None):
    grouped, explained = {}, set()
    for change in delta.changes if delta else ():
        if change.category == "dependencies":
            ecosystem = "npm" if change.source.startswith("npm-") else "python"
            key = (change.category, ecosystem, change.label.split("[", 1)[0])
            label = key[-1]
        elif change.source in {"agent-tools", "agent-models"}:
            key = (change.category, change.source, change.key.split(".", 1)[0])
            label = "Agent tool" if change.category == "tools" else "Agent model"
        elif change.category == "models":
            key, label = (change.category, change.source), change.source.replace("-project-model", " configured model").capitalize()
        else:
            key, label = (change.category, change.source, change.key), change.label
        entry = grouped.setdefault(key, {"category": change.category, "label": label, "details": [], "file": None})
        entry["details"].append(change.model_dump(mode="json"))
        if change.source in SOURCE_FILES:
            explained.add(SOURCE_FILES[change.source])
    result = [grouped[k] for k in sorted(grouped)]
    for change in files:
        # A possible rename has two paths; only suppress a single-path file
        # observation whose corresponding metadata change is actually present.
        if change.previous_path is None and change.path in explained:
            continue
        result.append({"category": "files", "label": change.path, "details": [], "file": change.model_dump(mode="json")})
    if delta and delta.passport_change == "changed":
        result.append({
            "category": "passport", "label": "Selected Passport / model reference changed",
            "details": [], "file": None,
            "before": before_passport.model_dump(mode="json") if before_passport else None,
            "after": after_passport.model_dump(mode="json") if after_passport else None,
        })
    return result


def counts(events):
    return {category: sum(e["category"] == category for e in events) for category in CATEGORIES}
