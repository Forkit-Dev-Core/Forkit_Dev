"""Tests for passport ID integrity verification, including case normalisation."""

import json
import subprocess
import sys
from pathlib import Path

from forkit.domain.integrity import verify_passport_id
from forkit.schemas import Architecture, LicenseType, ModelPassport, TaskType

CREATOR = {"name": "Hamza", "organization": "ForkIt"}
FAKE_HASH = "a" * 64


def make_model(**kwargs) -> ModelPassport:
    defaults = dict(
        name="llama-3-8b-ft",
        version="1.0.0",
        task_type=TaskType.TEXT_GENERATION,
        architecture=Architecture.DECODER_ONLY,
        creator=CREATOR,
        license=LicenseType.APACHE_2,
        artifact_hash=FAKE_HASH,
    )
    defaults.update(kwargs)
    return ModelPassport(**defaults)


def test_uppercase_artifact_hash_accepted() -> None:
    """Uppercase artifact_hash is normalised and still validates."""
    m = make_model()
    d = m.to_dict()
    d["artifact_hash"] = d["artifact_hash"].upper()
    result = verify_passport_id(d)
    assert result["valid"] is True
    assert result["reason"] == "ok"


def test_uppercase_stored_id_accepted() -> None:
    """Uppercase stored id is accepted for comparison."""
    m = make_model()
    d = m.to_dict()
    d["id"] = d["id"].upper()
    result = verify_passport_id(d)
    assert result["valid"] is True


def test_tampered_name_still_mismatches() -> None:
    """Tampering identity fields still fails verification."""
    m = make_model()
    d = m.to_dict()
    d["name"] = "tampered-name"
    result = verify_passport_id(d)
    assert result["valid"] is False
    assert result["reason"] == "id_mismatch"


def test_validator_script_accepts_uppercase_artifact_hash(tmp_path: Path) -> None:
    """The validate_passport.py script exits 0 for uppercase artifact_hash."""
    m = make_model()
    d = m.to_dict()
    d["artifact_hash"] = d["artifact_hash"].upper()
    passport_file = tmp_path / "passport.json"
    passport_file.write_text(json.dumps(d), encoding="utf-8")

    result = subprocess.run(
        [sys.executable, "scripts/validate_passport.py", "--path", str(passport_file)],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_malformed_artifact_hash_rejected() -> None:
    """Malformed (non-digest) artifact_hash is rejected even if stored ID matches a hash of it."""
    m = make_model()
    d = m.to_dict()
    bad_hash = "not-a-digest"
    d["artifact_hash"] = bad_hash
    # Recompute what a bad derived would be, but we expect rejection before match
    result = verify_passport_id(d)
    assert result["valid"] is False
    assert result["reason"] == "malformed_artifact_hash"
