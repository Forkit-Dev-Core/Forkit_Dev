"""Installed, account-free Passport → sessions → history → aggregate cards workflow."""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--require-os-denial", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "running", "platform": platform.platform(), "python": platform.python_version(),
              "checks": [], "network_attempts": 0, "os_denial_probes": {}}
    if args.require_os_denial:
        try:
            with socket.socket() as probe:
                probe.connect(("127.0.0.1", 9))
        except PermissionError:
            report["os_denial_probes"]["socket_connect_denied"] = True
        try:
            subprocess.run(["/usr/bin/true"], check=True)
        except PermissionError:
            report["os_denial_probes"]["unrelated_exec_denied"] = True
        assert len(report["os_denial_probes"]) == 2, "OS denial was not demonstrated"

    def audit(event, _args):
        if event in {"socket.connect", "socket.getaddrinfo", "socket.bind"}:
            report["network_attempts"] += 1
            raise AssertionError("Unexpected network use")

    sys.addaudithook(audit)
    from forkit_radar.sessions.cards import SessionCard

    from forkit.registry.local import LocalRegistry
    from forkit.schemas import AgentPassport, ModelPassport

    with tempfile.TemporaryDirectory(prefix="forkit-sharing-") as temporary:
        root = Path(temporary).resolve()
        project, store = root / "private-client-project", root / "state"
        project.mkdir()
        subprocess.run(["/usr/bin/git", "init", "-q", str(project)], check=True)

        def cli(*arguments, ok=True):
            result = subprocess.run([sys.executable, "-I", "-m", "forkit_radar.cli", *map(str, arguments)],
                                    cwd=project, capture_output=True, text=True, timeout=30)
            assert (result.returncode == 0) == ok, result.stderr
            return result.stdout

        model_input = root / "model-input.json"
        model_input.write_text(json.dumps({"passport_type": "model", "name": "PRIVATE_MODEL_774",
            "version": "1.0", "creator": {"name": "Local fixture"}, "task_type": "text-generation", "architecture": "transformer"}))
        model_path = root / "model.json"
        cli("passport", "create", "--input", model_input, "--output", model_path)
        model = ModelPassport.from_dict(json.loads(model_path.read_text()))
        agent = AgentPassport(name="PRIVATE_AGENT_881", version="1.0", creator={"name": "Fixture"},
                              model_id=model.id, task_type="code-assistant", architecture="ReAct")
        registry = LocalRegistry(root / "registry")
        registry.register_model(model)
        registry.register_agent(agent)
        report["checks"].append("local_passport_creation_without_account")
        common = ["--store", store]
        selection = ["--registry", registry.root, "--passport-id", agent.id]
        start = json.loads(cli("session", "start", "--tool", "codex", *common, *selection, "--json"))
        (project / "main.py").write_text("print('PRIVATE_SOURCE_CANARY_199')\n")
        cli("session", "stop", start["session_id"], *common)
        (project / "between.py").write_text("print('between sessions')\n")
        start = json.loads(cli("session", "start", "--tool", "codex", *common, *selection, "--json"))
        (project / "package.json").write_text(json.dumps({"dependencies": {"private-client-lib": "1.2.3"}}))
        (project / "feature.ts").write_text("export const ready = true;\n")
        (project / ".codex").mkdir()
        (project / ".codex/config.toml").write_text('model="private-model-ref"\n[mcp_servers.private_mcp]\ncommand="private-executable"\n')
        receipt = json.loads(cli("session", "stop", start["session_id"], *common, "--json"))
        assert receipt["passport_id"] == agent.id
        assert len(json.loads(cli("history", *common, "--json"))) == 2
        with sqlite3.connect(store / "sessions.sqlite3") as connection:
            before = list(connection.iterdump())
        for format in ("html", "svg", "json"):
            path = output / ("receipt." + format)
            cli("card", *common, "--output", path)
            raw = path.read_text()
            for private in (str(project), "PRIVATE_", "private-client", "private_mcp", "private-model-ref",
                            "private-executable", "feature.ts", agent.id, model.id, start["session_id"], "1.2.3"):
                assert private not in raw, private
            assert path.stat().st_mode & 0o777 == 0o600
            cli("card", *common, "--output", path, ok=False)
            assert path.read_text() == raw
        card = SessionCard.model_validate_json((output / "receipt.json").read_bytes())
        assert card.dependencies.added == 1 and card.tools.added >= 1 and card.models.added >= 1
        assert card.passport == "consistent"
        assert card.between_sessions.files == 1
        assert card.since_previous.files == card.file_changes + 1
        assert json.loads(cli("card", *common, "--json")) == card.model_dump(mode="json")
        with sqlite3.connect(store / "sessions.sqlite3") as connection:
            assert list(connection.iterdump()) == before
        report["checks"].extend(["installed_cli_two_sessions_and_history", "real_git_and_metadata_diffs",
            "existing_core_registry_association", "separate_between_session_diff", "private_canaries_absent_from_all_exports",
            "cards_do_not_mutate_history", "exclusive_0600_outputs", "aggregate_json_matches_file",
            "no_account_prompts_or_cloud_dependency"])
    assert report["network_attempts"] == 0
    report["status"] = "passed"
    (output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    print("Installed Passport, session history and local card workflow passed.")


if __name__ == "__main__":
    main()
