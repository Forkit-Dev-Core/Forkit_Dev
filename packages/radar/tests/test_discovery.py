"""Conformance and failure containment, not an independent accuracy benchmark."""

import builtins
import json
import os
import plistlib
import shutil
import socket
import struct
import subprocess
import sys
import time

import psutil
import pytest

from forkit_radar.cli import main
from forkit_radar.discovery import collectors, runner
from forkit_radar.discovery.catalog import APPLICATIONS, match_executable
from forkit_radar.discovery.collectors import MetadataError, read_bundle_metadata
from forkit_radar.discovery.scan import candidate_manifest, scan
from forkit_radar.discovery.types import Candidate, SourceResult, scope_keys


def forbidden(*_args, **_kwargs):
    raise AssertionError("forbidden collection or side effect")


@pytest.mark.parametrize(
    ("executable", "expected"),
    [
        ("/usr/local/bin/claude", "claude-code"),
        ("/opt/tools/codex", "codex-cli"),
        ("/opt/tools/ollama", "ollama-runtime"),
        ("/opt/tools/opencode", "opencode"),
        ("/Applications/Codex.app/Contents/MacOS/Codex", "codex"),
        ("/Applications/ChatGPT.app/Contents/MacOS/ChatGPT", "chatgpt-or-codex"),
        ("/Applications/Cursor.app/Contents/MacOS/Cursor", "cursor"),
        ("/Applications/Claude.app/Contents/MacOS/Claude", "claude-desktop"),
        ("/Applications/Windsurf.app/Contents/MacOS/Windsurf", "windsurf"),
        ("/Applications/Ollama.app/Contents/MacOS/Ollama", "ollama"),
        ("/opt/bin/python3", None),
        ("/opt/bin/node", None),
        ("/opt/bin/gemini", None),
        ("/opt/bin/goose", None),
        ("/opt/bin/jan", None),
        ("/opt/bin/claude-helper", None),
        ("/opt/bin/claude --token SENTINEL", None),
        ("/tmp/codex/Contents/MacOS/Electron", None),
        ("/Applications/Codex.app/Contents/Resources/codex", None),
        ("/Applications/Codex.app/Contents/MacOS/Codex (Renderer)", None),
        (
            "/Applications/Codex.app/Contents/Frameworks/Codex Helper.app/Contents/MacOS/Codex Helper",
            None,
        ),
        ("/Applications/Unrelated.app/Contents/MacOS/Cursor", None),
        ("/Applications/Cursor.app/Contents/MacOS/cursor", None),
        ("/tmp/../bin/claude", None),
        ("/tmp/\x1b/claude", None),
        ("claude", None),
        ("", None),
        ("/" + "x" * 4096 + "/claude", None),
    ],
)
def test_exact_executable_candidates_and_abstentions(executable, expected):
    match = match_executable(executable)
    assert (match[0] if match else None) == expected


def write_plist(path, data, *, fmt=plistlib.FMT_XML):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(plistlib.dumps(data, fmt=fmt))


def app_metadata(product, **overrides):
    return {
        "CFBundleIdentifier": product.bundle_id,
        "CFBundleExecutable": product.executable,
        "CFBundleShortVersionString": "1.2.3",
        "UnselectedCredential": "SENTINEL-SECRET",
        **overrides,
    }


@pytest.mark.parametrize("fmt", [plistlib.FMT_XML, plistlib.FMT_BINARY])
def test_bounded_metadata_read_filters_at_ingestion(tmp_path, fmt):
    path = tmp_path.resolve() / "Info.plist"
    write_plist(path, app_metadata(APPLICATIONS[0]), fmt=fmt)
    result = read_bundle_metadata(path)
    assert set(result) == {"CFBundleIdentifier", "CFBundleExecutable", "CFBundleShortVersionString"}
    assert "SENTINEL" not in json.dumps(result)


@pytest.mark.parametrize(("objects", "root", "table"), [(2**40, 0, 9), (1, 2, 9), (1, 0, 2**40)])
def test_binary_object_allocation_is_bounded_before_parsing(
    tmp_path, monkeypatch, objects, root, table
):
    path = tmp_path.resolve() / "Info.plist"
    path.write_bytes(b"bplist00\x00\x08" + struct.pack(">6xBBQQQ", 1, 1, objects, root, table))
    monkeypatch.setattr(plistlib, "loads", forbidden)
    with pytest.raises(MetadataError, match="invalid_metadata"):
        read_bundle_metadata(path)


@pytest.mark.parametrize(
    "kind",
    [
        "file_link",
        "parent_link",
        "fifo",
        "hardlink",
        "large",
        "duplicate",
        "malformed",
        "deep",
        "many",
        "entity",
    ],
)
def test_unsafe_or_malformed_bundle_metadata_is_rejected(tmp_path, kind):
    root = tmp_path.resolve()
    path = root / "Info.plist"
    if kind == "file_link":
        target = root / "private"
        target.write_text("SENTINEL-SECRET")
        path.symlink_to(target)
    elif kind == "parent_link":
        (root / "private").mkdir()
        (root / "linked").symlink_to(root / "private")
        path = root / "linked" / "Info.plist"
        path.write_text("SENTINEL-SECRET")
    elif kind == "fifo":
        os.mkfifo(path)
    elif kind == "hardlink":
        target = root / "private"
        target.write_text("SENTINEL-SECRET")
        os.link(target, path)
    elif kind == "large":
        path.write_bytes(b"X" * (collectors.MAX_METADATA_BYTES + 1))
    elif kind == "duplicate":
        path.write_bytes(
            b"<plist><dict><key>CFBundleIdentifier</key><string>a</string><key>CFBundleIdentifier</key><string>b</string></dict></plist>"
        )
    elif kind == "deep":
        value = "SENTINEL"
        for _ in range(20):
            value = [value]
        write_plist(path, {"nested": value})
    elif kind == "many":
        write_plist(path, {"nodes": [0] * 2050}, fmt=plistlib.FMT_BINARY)
    elif kind == "entity":
        path.write_bytes(
            b'<!DOCTYPE plist [<!ENTITY x SYSTEM "file:///SENTINEL-SECRET">]><plist><dict><key>x</key><string>&x;</string></dict></plist>'
        )
    else:
        path.write_bytes(b"SENTINEL-SECRET")
    started = time.monotonic()
    with pytest.raises((MetadataError, OSError)):
        read_bundle_metadata(path)
    assert time.monotonic() - started < 1


def test_replaced_file_during_read_is_inconclusive(tmp_path, monkeypatch):
    path = tmp_path.resolve() / "Info.plist"
    write_plist(path, app_metadata(APPLICATIONS[0]))
    original = os.stat

    def replace_then_stat(name, *args, **kwargs):
        if name == path.name:
            path.unlink()
            write_plist(path, app_metadata(APPLICATIONS[0]))
        return original(name, *args, **kwargs)

    monkeypatch.setattr(os, "stat", replace_then_stat)
    with pytest.raises(MetadataError, match="metadata_changed"):
        read_bundle_metadata(path)


def only_fixture_root(monkeypatch):
    original = read_bundle_metadata

    def read(path):
        if str(path).startswith("/Applications/"):
            raise FileNotFoundError()
        return original(path)

    monkeypatch.setattr(collectors, "read_bundle_metadata", read)


@pytest.mark.parametrize("product", APPLICATIONS, ids=lambda p: p.key)
def test_application_metadata_catalog_positive_and_absent(tmp_path, monkeypatch, product):
    only_fixture_root(monkeypatch)
    home = tmp_path.resolve()
    write_plist(
        home / "Applications" / product.bundle / "Contents/Info.plist", app_metadata(product)
    )
    results = list(collectors.applications(home, platform="darwin"))
    candidates = [c for r in results for c in r.candidates]
    assert len(candidates) == 1 and candidates[0].product == product.key
    assert candidates[0].version == "1.2.3"
    assert sum(r.status == "missing" for r in results) == 11
    assert "SENTINEL" not in str(results)


def test_observed_codex_bundle_variant_is_not_mislabeled(tmp_path, monkeypatch):
    only_fixture_root(monkeypatch)
    home = tmp_path.resolve()
    write_plist(
        home / "Applications/ChatGPT.app/Contents/Info.plist",
        {
            "CFBundleIdentifier": "com.openai.codex",
            "CFBundleExecutable": "ChatGPT",
            "CFBundleShortVersionString": "26.908.40834",
        },
    )
    candidates = [c for r in collectors.applications(home, platform="darwin") for c in r.candidates]
    assert [c.product for c in candidates] == ["codex"]


@pytest.mark.parametrize("bad", ["SENTINEL-SECRET", "\x1b[31m", "01.2-beta", 123, None])
def test_unrecognized_version_is_unknown_never_copied(tmp_path, monkeypatch, bad):
    only_fixture_root(monkeypatch)
    home = tmp_path.resolve()
    data = app_metadata(APPLICATIONS[0], CFBundleShortVersionString=bad)
    if bad is None:
        del data["CFBundleShortVersionString"]
    write_plist(
        home / "Applications/ChatGPT.app/Contents/Info.plist", data, fmt=plistlib.FMT_BINARY
    )
    candidates = [c for r in collectors.applications(home, platform="darwin") for c in r.candidates]
    assert len(candidates) == 1 and candidates[0].version is None


def test_one_bad_bundle_does_not_hide_other_sources(tmp_path, monkeypatch):
    def read(path):
        if "ChatGPT.app" in path.parts:
            raise PermissionError("SENTINEL-PRIVATE-PATH")
        if "Claude.app" in path.parts:
            return app_metadata(APPLICATIONS[1], CFBundleIdentifier="wrong.bundle")
        if "Codex.app" in path.parts:
            return app_metadata(APPLICATIONS[2])
        raise FileNotFoundError()

    monkeypatch.setattr(collectors, "read_bundle_metadata", read)
    results = list(collectors.applications(tmp_path, platform="darwin"))
    assert [r.status for r in results[:3]] == ["denied", "partial", "complete"]
    assert results[1].reason == "ambiguous_metadata" and not results[1].candidates
    assert len([c for r in results for c in r.candidates]) == 2
    assert "SENTINEL" not in str(results)


def fake_process_table(monkeypatch, entries):
    class FakeProcess:
        def __init__(self, pid):
            self.pid = pid

        def exe(self):
            value = entries[self.pid]
            if isinstance(value, Exception):
                raise value
            return value

        name = cmdline = environ = forbidden

    monkeypatch.setattr(psutil, "pids", lambda: list(range(len(entries))))
    monkeypatch.setattr(psutil, "Process", FakeProcess)


def test_partial_processes_survive_denial_and_disappearance_without_secret_collection(monkeypatch):
    fake_process_table(
        monkeypatch,
        [
            "/usr/local/bin/claude",
            psutil.AccessDenied(),
            psutil.NoSuchProcess(123),
            "",
            "/usr/bin/python3",
            "/usr/local/bin/claude",
        ],
    )
    (result,) = collectors.processes(platform="darwin")
    assert result.status == "partial" and result.reason == "process_visibility_limited"
    assert len(result.candidates) == 2  # Separate process observations, never name-based merging.


@pytest.mark.parametrize("value", ["", psutil.AccessDenied()])
def test_psutil_native_exe_fallback_cannot_read_command_line(monkeypatch, value):
    # Exercise the REAL pinned psutil public exe() implementation: both fallback
    # branches must be stopped before reaching native cmdline or environ APIs.
    monkeypatch.setattr(psutil, "pids", lambda: [os.getpid()])

    def native_exe(_self):
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(psutil._psplatform.Process, "exe", native_exe)
    monkeypatch.setattr(psutil._psplatform.Process, "cmdline", forbidden)
    monkeypatch.setattr(psutil._psplatform.Process, "environ", forbidden)
    (result,) = collectors.processes(platform=sys.platform)
    assert result.status == "partial" and not result.candidates


def test_process_list_failure_is_not_empty_success(monkeypatch):
    def denied():
        raise PermissionError("SENTINEL")

    monkeypatch.setattr(psutil, "pids", denied)
    (result,) = collectors.processes(platform="darwin")
    assert result.status == "denied" and result.reason == "process_table_unavailable"
    assert "SENTINEL" not in str(result)


@pytest.mark.parametrize(
    ("limit", "reason"), [("MAX_PROCESSES", "entry_limit"), ("MAX_CANDIDATES", "result_limit")]
)
def test_process_work_and_output_limits(monkeypatch, limit, reason):
    fake_process_table(monkeypatch, ["/bin/claude"] * 5)
    monkeypatch.setattr(collectors, limit, 2)
    (result,) = collectors.processes(platform="darwin")
    assert result.status == "partial" and result.reason == reason
    assert len(result.candidates) == 2


def test_cooperative_deadlines_are_explicit(monkeypatch, tmp_path):
    fake_process_table(monkeypatch, ["/bin/claude"])
    monkeypatch.setattr(collectors, "COLLECT_SECONDS", -1)
    (result,) = collectors.processes(platform="darwin")
    assert result.reason == "deadline_exceeded" and not result.candidates
    assert all(r.status == "timeout" for r in collectors.applications(tmp_path, platform="darwin"))


def test_unsupported_platform_does_not_inspect_sources(monkeypatch, tmp_path):
    monkeypatch.setattr(collectors, "read_bundle_metadata", forbidden)
    monkeypatch.setattr(psutil, "pids", forbidden)
    assert all(
        r.status == "unsupported" for r in collectors.applications(tmp_path, platform="linux")
    )
    assert all(r.status == "unsupported" for r in collectors.processes(platform="win32"))


def test_missing_optional_process_dependency_does_not_break_app_collector(monkeypatch, tmp_path):
    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name == "psutil":
            raise ImportError("SENTINEL")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    (result,) = collectors.processes(platform="darwin")
    assert result.reason == "dependency_unavailable"
    assert len(list(collectors.applications(tmp_path, platform="linux"))) == 12


def test_collectors_do_not_call_network_or_execute_programs(monkeypatch, tmp_path):
    fake_process_table(monkeypatch, ["/bin/claude", "/bin/node"])
    only_fixture_root(monkeypatch)
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(os, "system", forbidden)
    assert list(collectors.applications(tmp_path.resolve(), platform="darwin"))
    assert list(collectors.processes(platform="darwin"))


def test_worker_wall_timeout_terminates_owned_child(tmp_path):
    marker = tmp_path / "late-write"
    command = [
        sys.executable,
        "-I",
        "-c",
        "import sys,time,pathlib; time.sleep(0.7); pathlib.Path(sys.argv[1]).touch()",
        str(marker),
    ]
    started = time.monotonic()
    _, failure = runner._run_command(command, 0.1)
    assert failure == "deadline_exceeded" and time.monotonic() - started < 1
    time.sleep(0.75)
    assert not marker.exists()


def test_worker_output_and_stderr_are_bounded():
    raw, failure = runner._run_command(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.stderr.write('SENTINEL-SECRET'); sys.stdout.write('x'*300000)",
        ],
        3,
    )
    assert raw == b"" and failure == "worker_output_limit"


def source_line(scope, **overrides):
    return (
        json.dumps(
            {
                "scope": scope,
                "status": "missing",
                "reason": "not_found",
                "candidates": [],
                **overrides,
            }
        ).encode()
        + b"\n"
    )


def test_completed_sources_survive_worker_timeout_without_inventing_absence(monkeypatch):
    scopes = scope_keys("applications")
    monkeypatch.setattr(
        runner,
        "_run_command",
        lambda *_: (source_line(scopes[0]) + b'{"unfinished":', "deadline_exceeded"),
    )
    results = runner.run_worker("applications")
    assert results[0].status == "missing"
    assert all(r.status == "timeout" for r in results[1:])


@pytest.mark.parametrize(
    "raw",
    [
        b'{"SENTINEL-SECRET":true}\n',
        b'{"scope":NaN}\n',
        b"[]\n",
        source_line("unsupported-scope"),
        source_line(scope_keys("processes")[0]) * 2,
        source_line(
            scope_keys("processes")[0],
            candidates=[{"product": "SENTINEL", "version": None, "basis": "executable_metadata"}],
        ),
        source_line(scope_keys("processes")[0], status="complete", token="SENTINEL"),
        b"unfinished",
    ],
)
def test_invalid_worker_results_fail_closed_without_echoing_input(monkeypatch, raw):
    monkeypatch.setattr(runner, "_run_command", lambda *_: (raw, None))
    results = runner.run_worker("processes")
    assert all(r.status == "malformed" and not r.candidates for r in results)
    assert "SENTINEL" not in str(results)


def test_worker_execution_is_fixed_and_isolated(monkeypatch):
    called = []

    def capture(command, timeout):
        called.append((command, timeout))
        return b"", "collector_failed"

    monkeypatch.setattr(runner, "_run_command", capture)
    runner.run_worker("applications")
    assert called == [
        ([sys.executable, "-I", "-B", "-m", "forkit_radar.discovery.worker", "applications"], 3.0)
    ]


@pytest.mark.parametrize(
    "raw",
    [
        source_line(scope_keys("processes")[0], status="complete", reason="permission_denied"),
        source_line(
            scope_keys("processes")[0],
            status="complete",
            reason="process_table_read",
            candidates=[
                {"product": "claude-code", "version": "1.2", "basis": "executable_metadata"}
            ],
        ),
        source_line(
            scope_keys("processes")[0],
            status="complete",
            reason="process_table_read",
            candidates=[{"product": "codex", "version": None, "basis": "bundle_metadata"}],
        ),
    ],
)
def test_worker_cannot_promote_inconsistent_source_claims(monkeypatch, raw):
    monkeypatch.setattr(runner, "_run_command", lambda *_: (raw, None))
    (result,) = runner.run_worker("processes")
    assert result.status == "malformed" and not result.candidates


def test_bundle_candidate_cannot_claim_another_source(monkeypatch):
    raw = source_line(
        scope_keys("applications")[0],
        status="complete",
        reason="scoped_metadata_read",
        candidates=[{"product": "cursor", "version": "1.2", "basis": "bundle_metadata"}],
    )
    monkeypatch.setattr(runner, "_run_command", lambda *_: (raw, None))
    assert all(r.status == "malformed" for r in runner.run_worker("applications"))


def test_scan_never_enrolls_merges_or_invents_passports(monkeypatch):
    import importlib

    module = importlib.import_module("forkit_radar.discovery.scan")
    candidate = Candidate(product="claude-code", version=None, basis="executable_metadata")
    source = SourceResult(
        scope=scope_keys("processes")[0],
        status="partial",
        reason="process_visibility_limited",
        candidates=[candidate, candidate],
    )
    monkeypatch.setattr(module, "run_worker", lambda *_: (source,))
    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    report = scan(("processes",))
    manifests = [f.observation.manifest for f in report.sources[0].findings]
    assert manifests[0].provisional_component_key != manifests[1].provisional_component_key
    assert all(m.logical_agent_id is None and m.passport_id is None for m in manifests)
    assert all(m.measurement_completeness.identity == "partial" for m in manifests)
    assert all(
        f.evidence.runtime == "not_observed"
        and f.evidence.association == "unmatched"
        and f.evidence.passport == "unsupported"
        for f in report.sources[0].findings
    )
    assert report.storage == "not_saved" and report.continuity == "not_evaluated"
    assert all(s not in report.model_dump_json() for s in ("SENTINEL", "/Users/", "pid", "cmdline"))


def test_cli_requires_honest_unsaved_mode(capsys):
    with pytest.raises(SystemExit) as result:
        main(["scan"])
    assert result.value.code == 2
    assert "Invalid command" in capsys.readouterr().err


def test_candidate_manifest_has_no_discovered_claim_of_creator_or_identity():
    manifest = candidate_manifest(
        Candidate(product="codex", version="1.2.3", basis="bundle_metadata")
    )
    assert manifest.declared_identity.creator.origin == "unknown"
    assert manifest.logical_agent_id is None and manifest.passport_id is None


@pytest.mark.parametrize("selection", [(), ("applications", "applications"), ("injected-command",)])
def test_unknown_or_duplicate_scan_scopes_are_rejected(selection):
    with pytest.raises(ValueError, match="invalid_detector_selection"):
        scan(selection)


@pytest.mark.parametrize(("name", "expected"), [("claude", "claude-code"), ("claude-helper", None)])
def test_real_native_process_is_only_a_candidate_and_exit_is_partial(
    tmp_path, monkeypatch, name, expected
):
    # Controlled real OS fixture: an ordinary sleep binary renamed to look like
    # a product. This deliberately demonstrates the limit of executable metadata.
    executable = tmp_path.resolve() / name
    shutil.copyfile("/bin/sleep", executable)
    executable.chmod(0o700)
    process = subprocess.Popen(
        ["SENTINEL-PRIVATE-ARGV", "30"],
        executable=executable,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        deadline = time.monotonic() + 2
        while psutil.Process(process.pid).exe() != str(executable):
            if time.monotonic() >= deadline:
                pytest.fail("controlled native fixture did not start")
            time.sleep(0.01)
        monkeypatch.setattr(psutil, "pids", lambda: [process.pid])
        monkeypatch.setattr(psutil._psplatform.Process, "cmdline", forbidden)
        monkeypatch.setattr(psutil._psplatform.Process, "environ", forbidden)
        monkeypatch.setattr(socket, "socket", forbidden)
        monkeypatch.setattr(socket, "getaddrinfo", forbidden)
        monkeypatch.setattr(subprocess, "Popen", forbidden)
        (result,) = collectors.processes(platform=sys.platform)
        assert result.status == "complete"
        assert [c.product for c in result.candidates] == ([expected] if expected else [])
        assert "SENTINEL" not in result.model_dump_json()
        for candidate in result.candidates:
            manifest = candidate_manifest(candidate)
            assert manifest.logical_agent_id is None and manifest.passport_id is None
        process.terminate()
        process.wait(timeout=2)
        (gone,) = collectors.processes(platform=sys.platform)
        assert gone.status == "partial" and not gone.candidates
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=2)
