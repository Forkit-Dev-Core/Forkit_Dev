import json

import pytest
from typer.testing import CliRunner

from forkit.cli import main as cli
from forkit.registry import LocalRegistry
from forkit.schemas import ModelPassport


@pytest.mark.parametrize(
    ("fields", "target"),
    [
        ({"metadata": {"source_url": "https://github.com/example-org/sample"}},
         "https://raw.githubusercontent.com/example-org/sample/HEAD/.well-known/forkit-verify.txt"),
        ({"hub_url": "https://huggingface.co/example-org/sample"},
         "https://huggingface.co/example-org/sample/resolve/main/.well-known/forkit-verify.txt"),
    ],
)
def test_hosted_proof_uses_source_fields_preserved_by_registry(tmp_path, monkeypatch, fields, target):
    monkeypatch.setattr(cli, "_REGISTRY_ROOT", tmp_path)
    passport = ModelPassport(
        name="example-model", version="1.0", creator={"name": "Example Lab"},
        task_type="other", architecture="other", **fields,
    )
    LocalRegistry(tmp_path).register_model(passport)

    result = CliRunner().invoke(cli.app, ["hosted-proof", passport.id])

    assert result.exit_code == 0, result.output
    proof = json.loads(result.output)
    assert proof["verify_url"] == target
    assert proof["proof_line"] == f"forkit-passport-id={passport.id}"
