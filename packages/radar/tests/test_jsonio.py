import json

import pytest

from forkit_radar.jsonio import (
    MAX_DOCUMENT_BYTES,
    MAX_NODES,
    MAX_STRING_LENGTH,
    ContractError,
    load_json,
)


@pytest.mark.parametrize(
    ("raw", "code"),
    [
        (b'{"id":1,"id":2}', "duplicate_key"),
        (b'{"nested":{"id":1,"id":2}}', "duplicate_key"),
        (b'{"a":1,"\\u0061":2}', "duplicate_key"),
        (b'{"x":NaN}', "non_finite_number"),
        (b'{"x":Infinity}', "non_finite_number"),
        (b'{"x":-Infinity}', "non_finite_number"),
        (b'{"x":1.0}', "non_integer_number"),
        (b'{"x":1e0}', "non_integer_number"),
        (b'{"x":9007199254740992}', "integer_out_of_range"),
        (b'{"x":-9007199254740992}', "integer_out_of_range"),
        (b'{"x":"\\ud800"}', "invalid_unicode"),
        (b'{"\\udfff":0}', "invalid_unicode"),
        (b'{"x":"\xff"}', "invalid_json"),
        (b"\xef\xbb\xbf{}", "invalid_json"),
        (b"{} trailing", "invalid_json"),
        (b"[]", "object_required"),
        (b"null", "object_required"),
    ],
)
def test_wire_rejections_are_non_disclosing(raw, code):
    with pytest.raises(ContractError) as exc:
        load_json(raw)
    assert str(exc.value) == code


def test_json_budget_limits():
    examples = [
        (b" " * (MAX_DOCUMENT_BYTES + 1), "document_too_large"),
        (b'{"x":' + b"[" * 40 + b"0" + b"]" * 40 + b"}", "too_deep"),
        (json.dumps({"x": "a" * (MAX_STRING_LENGTH + 1)}).encode(), "string_too_long"),
        (json.dumps({"x": [0] * MAX_NODES}).encode(), "too_many_nodes"),
    ]
    for raw, expected in examples:
        with pytest.raises(ContractError, match=f"^{expected}$"):
            load_json(raw)


def test_deeply_nested_malformed_input_never_leaks_recursion_error():
    raw = b'{"x":' + b"[" * 2000 + b"0" + b"]" * 2000 + b"}"
    with pytest.raises(ContractError):
        load_json(raw)


def test_interoperable_boundaries_and_decimal_strings_survive():
    data = {
        "min": -(2**53 - 1),
        "max": 2**53 - 1,
        "decimal": "0.25",
        "unicode": "😀",
        "absent": None,
        "empty": [],
    }
    assert load_json(json.dumps(data).encode()) == data


def test_non_bytes_input_is_not_coerced():
    with pytest.raises(ContractError, match="bytes_required"):
        load_json("{}")
