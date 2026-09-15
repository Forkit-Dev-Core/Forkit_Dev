"""Fixed Radar-owned collector worker. Never runs a discovered program."""

import os
import sys
import unicodedata
from pathlib import Path


def main() -> int:
    from ..jsonio import load_json
    from .types import DETECTORS

    if len(sys.argv) not in {2, 3} or sys.argv[1] not in DETECTORS:
        return 2
    # Import failures and native crashes are contained by the parent. Stderr is
    # discarded there, so exceptions cannot disclose paths or input values.
    from .collectors import applications, processes

    try:
        options = load_json(sys.argv[2].encode()) if len(sys.argv) == 3 else {}
        if set(options) - {"project", "models_root", "agent_file"}:
            return 2
        for value in options.values():
            if type(value) is not str or not 0 < len(value) <= 4096:
                return 2
            if (
                not Path(value).is_absolute()
                or ".." in Path(value).parts
                or len(Path(value).parts) > 16
                or any(unicodedata.category(c) in {"Cc", "Cf", "Cs"} for c in value)
            ):
                return 2
        home = Path.home()
        project = Path(options["project"]) if "project" in options else None
        detector = sys.argv[1]
        if detector == "applications":
            results = applications(home)
        elif detector == "processes":
            results = processes()
        elif detector == "codex-mcp":
            from .mcp import codex

            configured_home = os.environ.get("CODEX_HOME")
            codex_home = Path(configured_home) if configured_home else home / ".codex"
            results = codex(home, project, codex_home=codex_home)
        elif detector == "cursor-mcp":
            from .mcp import cursor

            results = cursor(home, project)
        elif detector == "ollama":
            from .ollama import ollama

            root = options.get("models_root") or os.environ.get("OLLAMA_MODELS")
            results = ollama(Path(root) if root else home / ".ollama/models")
        elif detector == "langgraph":
            from .agents import langgraph

            results = langgraph(project)
        else:
            from .agents import agent_manifest

            results = agent_manifest(
                Path(options["agent_file"]) if "agent_file" in options else None
            )
        for result in results:
            print(result.model_dump_json(), flush=True)
    except Exception:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
