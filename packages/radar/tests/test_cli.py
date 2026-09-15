import json
import os
import socket
import subprocess
from pathlib import Path

import pytest

from forkit_radar.cli import main

FIXTURES = Path(__file__).parent / "fixtures"


def test_help_explains_the_current_boundary(capsys):
    assert main([]) == 0
    assert "not implemented yet" in capsys.readouterr().out


def test_validation_is_not_reported_as_authenticity(capsys, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("unexpected side effect")

    monkeypatch.setattr(socket, "socket", forbidden)
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    monkeypatch.setattr(subprocess, "Popen", forbidden)
    monkeypatch.setattr(Path, "home", forbidden)
    assert main(["validate", "manifest", str(FIXTURES / "manifest.json")]) == 0
    assert "authenticity have not been verified" in capsys.readouterr().out


def test_invalid_input_and_paths_are_not_echoed(tmp_path, capsys):
    path = tmp_path / "SENTINEL-PRIVATE-PATH.json"
    path.write_text('{"SENTINEL-SECRET":NaN}')
    assert main(["validate", "manifest", str(path)]) == 2
    output = capsys.readouterr()
    assert "SENTINEL" not in output.out + output.err
    assert "non_finite_number" in output.err
    assert main(["validate", "manifest", str(path) + "-absent"]) == 2
    assert "SENTINEL" not in capsys.readouterr().err


def test_schema_command_emits_shape_without_reading_input(capsys):
    assert main(["schema", "manifest"]) == 0
    schema = json.loads(capsys.readouterr().out)
    assert schema["additionalProperties"] is False
    assert "logical_agent_id" in schema["required"]


def test_symlink_and_fifo_input_are_rejected_without_blocking(tmp_path, capsys):
    link = tmp_path / "symlink"
    link.symlink_to(FIXTURES / "manifest.json")
    assert main(["validate", "manifest", str(link)]) == 2
    fifo = tmp_path / "fifo"
    os.mkfifo(fifo)
    assert main(["validate", "manifest", str(fifo)]) == 2
    assert "regular_file_required" in capsys.readouterr().err


def test_unknown_contract_does_not_echo_input(capsys):
    assert main(["schema", "SENTINEL-SECRET"]) == 2
    assert "SENTINEL" not in capsys.readouterr().err


def test_invalid_arguments_do_not_echo_input(capsys):
    with pytest.raises(SystemExit) as result:
        main(["SENTINEL-SECRET"])
    assert result.value.code == 2
    assert "SENTINEL" not in capsys.readouterr().err


def test_version_does_not_import_optional_verifiers(capsys, monkeypatch):
    import builtins

    original = builtins.__import__

    def import_without_crypto(name, *args, **kwargs):
        if name.startswith(("cryptography", "rfc8785")):
            raise ImportError("verifier unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", import_without_crypto)
    with pytest.raises(SystemExit) as exit_status:
        main(["--version"])
    assert exit_status.value.code == 0
    assert capsys.readouterr().out.strip() == "forkit-radar 0.1.0b3"
