"""Version validation must agree across the dataclass and Pydantic backends."""

from importlib import import_module

import pytest

from forkit.domain.identity import validate_version

VALID_VERSIONS = ["1.0", "1.0.0", "2.4.1", "0.1", "0.0.0", "12345678901234567890.0"]
INVALID_VERSIONS = [
    "1",
    "1.0.0.0",
    "v1.0.0",
    "latest",
    "a.b",
    "1..0",
    ".1",
    "1.",
    " .",
    "-1.0",
    "+1.0",
    " 1.0",
    "1.0 ",
    "1.0\n",
    "1.0-rc1",
    "1.0+build",
    "\u0661.0",
    "1.\u00b2",
]


@pytest.mark.parametrize("version", VALID_VERSIONS)
def test_validate_version_preserves_valid_input(version):
    assert validate_version(version) == version


@pytest.mark.parametrize("version", INVALID_VERSIONS)
def test_validate_version_rejects_invalid_input(version):
    with pytest.raises(ValueError, match="Version must be"):
        validate_version(version)


@pytest.mark.parametrize("value", [None, 1, True, ["1.0"], {"version": "1.0"}])
def test_validate_version_rejects_malformed_non_string_input(value):
    with pytest.raises(ValueError, match="Version must be"):
        validate_version(value)


def test_validate_version_preserves_existing_numeric_input_handling():
    assert validate_version(1.5) == 1.5


@pytest.fixture(params=["model", "agent", "pydantic.model", "pydantic.agent"])
def make_passport(request):
    module_name = request.param
    if module_name.startswith("pydantic."):
        pytest.importorskip("pydantic", minversion="2.0")
    kind = module_name.rsplit(".", 1)[-1]
    module = import_module(f"forkit.schemas.{module_name}")
    passport_class = getattr(module, f"{kind.title()}Passport")
    kwargs = {"name": "test-passport", "creator": {"name": "Test creator"}}
    if kind == "model":
        kwargs.update(task_type="text-generation", architecture="decoder-only")
    else:
        kwargs.update(model_id="a" * 64, task_type="customer-support", architecture="ReAct")
    return lambda version: passport_class(version=version, **kwargs)


@pytest.mark.parametrize("version", VALID_VERSIONS)
def test_passport_preserves_valid_version_and_identity(make_passport, version):
    passport = make_passport(version)
    restored = type(passport).from_dict(passport.to_dict())
    assert restored.version == version
    assert restored.id == passport.id


@pytest.mark.parametrize("version", INVALID_VERSIONS)
def test_passport_rejects_invalid_version(make_passport, version):
    with pytest.raises(ValueError, match="Version must be"):
        make_passport(version)
