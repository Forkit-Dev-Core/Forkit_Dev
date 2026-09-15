"""Adversarial metadata cases and installed-worker/framework integration."""

from __future__ import annotations

import importlib.util
import json
import os
import socket
import subprocess
import sys
from pathlib import Path
from uuid import uuid4

import pytest
from pydantic import ValidationError

from forkit_radar.discovery import agents, mcp, metadata, ollama
from forkit_radar.discovery.runner import run_worker
from forkit_radar.discovery.scan import scan
from forkit_radar.discovery.types import MetadataCandidate, ScanReport

FIXTURES = Path(__file__).parent / "fixtures"
SECRET = "DO_NOT_EXPORT_7f42"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value if isinstance(value, str) else json.dumps(value))
    return path


def wire(results):
    return "\n".join(r.model_dump_json() for r in results)


def model_document():
    return json.loads((FIXTURES / "adapters/ollama-llama3.2-manifest.json").read_bytes())


def model_file(root, value=None, tag="latest"):
    return write(
        root / f"manifests/registry.example/library/{SECRET}/{tag}",
        model_document() if value is None else value,
    )


def test_codex_real_toml_types_and_secrets_do_not_cross_boundary(tmp_path):
    write(
        tmp_path / ".codex/config.toml",
        f'''
model = "{SECRET}"
unrelated_decimal = 0.25
unrelated_date = 2026-09-14
[mcp_servers."{SECRET}"]
command = "${{DO_NOT_EXPAND}}/some-program"
args = ["--secret", "{SECRET}"]
env = {{ TOKEN = "{SECRET}" }}
enabled = false
[mcp_servers.remote]
url = "https://{SECRET}.invalid/mcp"
http_headers = {{ Authorization = "{SECRET}" }}
''',
    )
    project = tmp_path / "project"
    write(project / ".codex/config.toml", '[mcp_servers.remote]\nurl="https://example.invalid"')
    results = list(mcp.codex(tmp_path, project))
    assert [r.status for r in results] == ["complete", "complete"]
    assert [c.detail.transport for c in results[0].candidates] == ["stdio", "http"]
    assert [c.detail.activation for c in results[0].candidates] == ["disabled", "enabled"]
    assert results[1].candidates[0].detail.precedence == "project_trust_unknown"
    assert results[0].candidates[0].detail.precedence == "layer_only"
    assert SECRET not in wire(results) and "some-program" not in wire(results)
    for r in results:
        for c in r.candidates:
            assert c.manifest.tools is None
            assert c.manifest.declared_identity.name.origin == "unknown"


@pytest.mark.parametrize(
    "raw",
    [
        '[mcp_servers.x]\ncommand="one"\ncommand="two"',
        '[mcp_servers.x]\ncommand="one"\nv=nan',
        '[mcp_servers.x]\ncommand="one"\nv=inf',
        '[mcp_servers.x]\ncommand="one"\nv=9007199254740992',
        "mcp_servers = []",
        "x=" + "[" * 40 + "0" + "]" * 40,
        "mcp_servers = {",
    ],
)
def test_codex_malformed_is_not_empty(tmp_path, raw):
    write(tmp_path / ".codex/config.toml", raw)
    result = next(mcp.codex(tmp_path))
    assert result.status == "malformed" and not result.candidates


def test_codex_home_override(tmp_path):
    write(tmp_path / ".codex/config.toml", "INVALID")
    write(tmp_path / "custom/config.toml", '[mcp_servers.x]\ncommand="anything"')
    assert next(mcp.codex(tmp_path, codex_home=tmp_path / "custom")).status == "complete"


def test_cursor_project_precedence_preserves_both_declarations(tmp_path):
    write(
        tmp_path / ".cursor/mcp.json",
        {
            "mcpServers": {
                SECRET: {"command": SECRET, "args": [SECRET]},
                "other": {"url": f"https://{SECRET}.invalid", "headers": {"Authorization": SECRET}},
            }
        },
    )
    project = tmp_path / "selected"
    write(
        project / ".cursor/mcp.json", {"mcpServers": {SECRET: {"url": "https://example.invalid"}}}
    )
    user, local = mcp.cursor(tmp_path, project)
    assert [c.detail.precedence for c in user.candidates] == ["shadowed", "selected_sources_only"]
    assert local.candidates[0].detail.precedence == "selected_sources_only"
    assert all(c.detail.activation == "unknown" for c in (*user.candidates, *local.candidates))
    assert SECRET not in wire([user, local])


@pytest.mark.parametrize(
    "local",
    [
        '{"mcpServers":',
        {"mcpServers": {SECRET: {"command": 12}}},
        {"mcpServers": {SECRET: {"url": "https://example.invalid", "command": "x"}}},
        {"mcpServers": {SECRET: {}}},
        {"mcpServers": {SECRET: {"command": "line\nbreak"}}},
        {"mcpServers": []},
    ],
)
def test_cursor_bad_higher_layer_does_not_assume_global_fallback(tmp_path, local):
    write(tmp_path / ".cursor/mcp.json", {"mcpServers": {SECRET: {"command": "good"}}})
    project = tmp_path / "selected"
    write(project / ".cursor/mcp.json", local)
    user, local = mcp.cursor(tmp_path, project)
    assert user.status == "partial" and user.reason == "precedence_unresolved"
    assert user.candidates[0].detail.precedence == "unresolved"
    assert local.status in {"partial", "malformed"}


@pytest.mark.parametrize("mode", ["missing", "empty", "unselected"])
def test_cursor_known_selected_scope_without_override(tmp_path, mode):
    write(tmp_path / ".cursor/mcp.json", {"mcpServers": {"x": {"command": "good"}}})
    project = tmp_path / "selected"
    if mode == "empty":
        write(project / ".cursor/mcp.json", {"mcpServers": {}})
    user, local = mcp.cursor(tmp_path, None if mode == "unselected" else project)
    assert user.status == "complete"
    assert user.candidates[0].detail.precedence == "selected_sources_only"
    assert (
        local.status
        == {"missing": "missing", "empty": "complete", "unselected": "unsupported"}[mode]
    )


def test_denial_and_unsafe_project_do_not_remove_lower_layer(tmp_path, monkeypatch):
    write(tmp_path / ".cursor/mcp.json", {"mcpServers": {"x": {"command": "good"}}})
    project = tmp_path / "selected"
    target = write(project / ".cursor/mcp.json", {"mcpServers": {}})
    original = metadata.read_metadata

    def denied(path):
        if path == target:
            raise PermissionError(SECRET)
        return original(path)

    monkeypatch.setattr(metadata, "read_metadata", denied)
    user, local = mcp.cursor(tmp_path, project)
    assert local.status == "denied" and user.candidates[0].detail.precedence == "unresolved"
    assert SECRET not in wire([user, local])
    monkeypatch.setattr(metadata, "read_metadata", original)
    target.unlink()
    target.symlink_to(tmp_path / ".cursor/mcp.json")
    user, local = mcp.cursor(tmp_path, project)
    assert local.reason == "symlink_or_unsafe_file"
    assert user.candidates[0].detail.precedence == "unresolved"


def test_adapter_limits_retain_partial_candidates(tmp_path):
    write(
        tmp_path / ".cursor/mcp.json",
        {"mcpServers": {f"s{i}": {"command": "x"} for i in range(40)}},
    )
    result = next(mcp.cursor(tmp_path))
    assert len(result.candidates) == 32 and result.unknown_entries == 8
    assert result.status == "partial" and result.reason == "entry_limit"
    write(tmp_path / ".codex/config.toml", "#" + "x" * 65536)
    assert next(mcp.codex(tmp_path)).reason == "metadata_too_large"


def test_public_ollama_manifest_is_declared_not_measured():
    candidate = ollama.parse_manifest(json.dumps(model_document()).encode(), 1)
    assert candidate.detail.declared_bytes > 1_000_000
    assert candidate.manifest.artifacts[0].digest.origin == "declared"
    assert candidate.manifest.artifacts[0].hashing_profile == "unknown"
    assert candidate.manifest.declared_identity.name.origin == "unknown"


@pytest.mark.parametrize(
    "mutation",
    [
        "array",
        "duplicate",
        "bool_size",
        "negative",
        "huge",
        "bad_digest",
        "no_model",
        "too_many",
        "float",
    ],
)
def test_ollama_rejects_invalid_manifest(mutation):
    data = model_document()
    if mutation == "array":
        data = []
    elif mutation == "duplicate":
        with pytest.raises(ValueError):
            ollama.parse_manifest(b'{"schemaVersion":2,"schemaVersion":2}', 1)
        return
    elif mutation in {"bool_size", "negative", "huge", "float"}:
        data["layers"][0]["size"] = {
            "bool_size": True,
            "negative": -1,
            "huge": 2**53,
            "float": 0.5,
        }[mutation]
    elif mutation == "bad_digest":
        data["layers"][0]["digest"] = SECRET
    elif mutation == "no_model":
        data["layers"] = [data["config"]]
    elif mutation == "too_many":
        data["layers"] = [data["layers"][0]] * 5
    with pytest.raises(ValueError):
        ollama.parse_manifest(json.dumps(data).encode(), 1)


def test_ollama_partial_inventory_never_opens_blobs_or_aliases(tmp_path, monkeypatch):
    model_file(tmp_path)
    model_file(tmp_path, "[]", "bad")
    write(tmp_path / "blobs/DO_NOT_READ", SECRET)
    calls = []
    original = ollama.read_at

    def observe(parent, name, limit):
        calls.append(name)
        assert name in {"latest", "bad"}
        return original(parent, name, limit)

    monkeypatch.setattr(ollama, "read_at", observe)
    result = next(ollama.ollama(tmp_path))
    assert result.status == "partial" and result.unknown_entries == 1
    assert len(result.candidates) == 1 and len(calls) == 2
    assert SECRET not in wire([result])


@pytest.mark.parametrize(
    "kind", ["symlink_file", "symlink_directory", "hardlink", "oversized", "fifo"]
)
def test_model_unsafe_entries_are_incomplete(tmp_path, kind):
    path = model_file(tmp_path)
    if kind == "symlink_directory":
        (tmp_path / "manifests/escape").symlink_to(tmp_path, target_is_directory=True)
    elif kind == "hardlink":
        os.link(path, path.with_name("linked"))
    else:
        path.unlink()
        if kind == "symlink_file":
            path.symlink_to(write(tmp_path / "secret", SECRET))
        elif kind == "oversized":
            path.write_bytes(b"x" * 65537)
        else:
            os.mkfifo(path)
    result = next(ollama.ollama(tmp_path))
    assert result.status == "partial" and result.unknown_entries >= 1
    assert SECRET not in wire([result])


def test_model_result_limit_and_unknown_empty_distinction(tmp_path):
    assert next(ollama.ollama(tmp_path)).status == "missing"
    (tmp_path / "manifests").mkdir()
    assert next(ollama.ollama(tmp_path)).status == "complete"
    for i in range(33):
        model_file(tmp_path, tag=f"v{i}")
    result = next(ollama.ollama(tmp_path))
    assert result.status == "partial" and result.reason == "result_limit"
    assert len(result.candidates) == 32 and result.unknown_entries >= 1


@pytest.mark.parametrize(
    "reference",
    ["./agent.py:graph", "agent.py:graph", "pkg.agent:graph", "pkg/agent.py:create_graph"],
)
def test_selected_langgraph_python_references_do_not_load_source(tmp_path, reference, monkeypatch):
    write(
        tmp_path / "langgraph.json",
        {"graphs": {SECRET: reference}, "env": SECRET, "dependencies": [SECRET]},
    )
    write(tmp_path / "agent.py", f'raise RuntimeError("{SECRET}")')
    calls = []
    original = metadata.read_metadata

    def only_metadata(path):
        calls.append(path)
        assert path == tmp_path / "langgraph.json"
        return original(path)

    monkeypatch.setattr(metadata, "read_metadata", only_metadata)
    result = next(agents.langgraph(tmp_path))
    assert result.status == "complete" and len(calls) == 1
    assert SECRET not in wire([result])
    assert result.candidates[0].manifest.tools is None
    assert next(agents.langgraph(None)).reason == "project_not_selected"


@pytest.mark.parametrize(
    "reference",
    [
        "../escape.py:graph",
        "/absolute.py:graph",
        "agent.js:graph",
        {"path": "agent.py"},
        12,
        "agent.py",
        "agent.py:call()",
    ],
)
def test_unknown_graph_form_keeps_other_candidates(tmp_path, reference):
    write(tmp_path / "langgraph.json", {"graphs": {"good": "agent.py:graph", "unknown": reference}})
    result = next(agents.langgraph(tmp_path))
    assert result.status == "partial" and result.unknown_entries == 1
    assert len(result.candidates) == 1


def test_selected_manifest_strips_copied_identity_and_downgrades_claims(tmp_path):
    data = json.loads((FIXTURES / "manifest.json").read_bytes())
    data["logical_agent_id"] = str(uuid4())
    data["provisional_component_key"] = None
    data["passport_id"] = "a" * 64
    data["declared_identity"]["name"]["origin"] = "independently_measured"
    path = write(tmp_path / "agent.json", data)
    first, second = next(agents.agent_manifest(path)), next(agents.agent_manifest(path))
    a, b = first.candidates[0].manifest, second.candidates[0].manifest
    assert a.logical_agent_id is None
    assert a.provisional_component_key != b.provisional_component_key
    assert a.passport_id == "a" * 64
    assert a.declared_identity.name.origin == "declared"
    assert a.settings.origin == "declared"
    assert a.tools == ()  # Explicit declaration of empty is different from unobserved.


@pytest.mark.parametrize(
    "field,value", [("command", SECRET), ("component_kind", "model"), ("schema_version", "999")]
)
def test_explicit_agent_manifest_rejects_unsupported_shapes(tmp_path, field, value):
    data = json.loads((FIXTURES / "manifest.json").read_bytes())
    data[field] = value
    result = next(agents.agent_manifest(write(tmp_path / "agent.json", data)))
    assert result.status == "malformed" and SECRET not in wire([result])


@pytest.mark.parametrize(
    "claim",
    [
        "identity",
        "logical",
        "passport",
        "runtime_profile",
        "wrong_adapter",
        "independent_digest",
        "private_artifact_key",
        "wrong_transport",
    ],
)
def test_parent_boundary_rejects_worker_escalation(claim):
    raw = ollama.parse_manifest(json.dumps(model_document()).encode(), 1).model_dump()
    if claim == "identity":
        raw["manifest"]["declared_identity"]["name"] = {"value": SECRET, "origin": "declared"}
        raw["manifest"]["measurement_completeness"]["identity"] = "partial"
    elif claim == "logical":
        raw["manifest"]["logical_agent_id"] = str(uuid4())
        raw["manifest"]["provisional_component_key"] = None
    elif claim == "passport":
        raw["manifest"]["passport_id"] = "a" * 64
    elif claim == "runtime_profile":
        raw["manifest"]["scope_profile"]["profile_id"] = "runtime-adapter-v1"
    elif claim == "wrong_adapter":
        raw["detail"]["adapter"] = "langgraph"
    elif claim == "independent_digest":
        raw["manifest"]["artifacts"][0]["digest"]["origin"] = "independently_measured"
        raw["manifest"]["artifacts"][0]["hashing_profile"] = "core-file-sha256-v1"
    elif claim == "private_artifact_key":
        raw["manifest"]["artifacts"][0]["key"] = SECRET
    else:
        raw["detail"]["transport"] = "http"
    with pytest.raises(ValidationError):
        MetadataCandidate.model_validate(raw)


def test_no_metadata_adapter_executes_or_connects(tmp_path, monkeypatch):
    marker = tmp_path / "executed"
    write(tmp_path / ".cursor/mcp.json", {"mcpServers": {SECRET: {"command": f"touch {marker}"}}})
    write(tmp_path / ".codex/config.toml", f'[mcp_servers.x]\nurl="https://{SECRET}.invalid"')
    write(tmp_path / "langgraph.json", {"graphs": {"x": "agent.py:graph"}})
    model_file(tmp_path / "models")

    def forbidden(*args, **kwargs):
        raise AssertionError("network_or_execution_attempt")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    results = [
        *mcp.cursor(tmp_path),
        *mcp.codex(tmp_path),
        *agents.langgraph(tmp_path),
        *ollama.ollama(tmp_path / "models"),
    ]
    assert all(r.status in {"complete", "unsupported"} for r in results)
    assert SECRET not in wire(results) and not marker.exists()


def test_installed_workers_and_cli_selected_metadata(tmp_path, monkeypatch):
    # Workers use isolated installed wheels, so this test also detects stale builds.
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / ".codex"))
    write(tmp_path / ".cursor/mcp.json", {"mcpServers": {SECRET: {"command": SECRET}}})
    write(tmp_path / ".codex/config.toml", f'[mcp_servers."{SECRET}"]\ncommand="{SECRET}"')
    project = tmp_path / "selected"
    write(project / "langgraph.json", {"graphs": {SECRET: "agent.py:graph"}})
    model_file(tmp_path / "models")
    data = json.loads((FIXTURES / "manifest.json").read_bytes())
    data["passport_id"] = "a" * 64
    data["declared_identity"]["name"]["value"] = SECRET
    agent_file = write(tmp_path / "agent.json", data)
    report = scan(
        ("codex-mcp", "cursor-mcp", "ollama", "langgraph", "agent-manifest"),
        project=project,
        models_root=tmp_path / "models",
        agent_file=agent_file,
    )
    assert report.candidate_count == 5 and len(report.sources) == 7
    assert report.storage == "not_saved"
    for source in report.sources:
        for f in source.findings:
            assert f.evidence.runtime == "not_observed"
            assert f.evidence.passport == "unsupported"
            if f.observation.manifest:
                assert f.observation.manifest.logical_agent_id is None
                assert f.evidence.association == (
                    "declared" if source.detector == "agent-manifest" else "unmatched"
                )
    command = [
        sys.executable,
        "-I",
        "-m",
        "forkit_radar.cli",
        "scan",
        "--no-save",
        "--source",
        "agents",
        "--project",
        str(project),
        "--agent-manifest",
        str(agent_file),
    ]
    result = subprocess.run(command, capture_output=True, timeout=8, cwd="/")
    assert result.returncode == 0 and result.stderr == b""
    assert SECRET.encode() not in result.stdout and str(tmp_path).encode() not in result.stdout
    result = subprocess.run([*command, "--json"], capture_output=True, timeout=8, cwd="/")
    private = ScanReport.model_validate_json(result.stdout)
    assert private.candidate_count == 2
    assert SECRET.encode() in result.stdout  # Explicit selected manifest is private JSON.
    assert run_worker("langgraph")[0].reason == "project_not_selected"


@pytest.mark.parametrize("option", ["../outside", "bad\npath", "x/" * 20])
def test_invalid_selection_never_reaches_worker(tmp_path, option):
    with pytest.raises(ValueError, match="invalid_scope_selection"):
        scan(("langgraph",), project=tmp_path / option)


def test_real_langchain_agent_tool_loop_and_passive_langgraph_integration():
    # This fixture is deliberately executed by the test, never by the scanner.
    project = FIXTURES / "adapters/langgraph_project"
    spec = importlib.util.spec_from_file_location("radar_owned_agent_fixture", project / "agent.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    from langchain_core.messages import ToolMessage

    result = module.graph.invoke({"messages": [{"role": "user", "content": "Add 2 and 3"}]})
    assert [m.content for m in result["messages"] if isinstance(m, ToolMessage)] == ["5"]
    assert result["messages"][-1].content == "5"
    found = next(agents.langgraph(project.resolve()))
    assert found.status == "complete" and len(found.candidates) == 1
    assert found.candidates[0].manifest.tools is None
    assert found.candidates[0].manifest.logical_agent_id is None
