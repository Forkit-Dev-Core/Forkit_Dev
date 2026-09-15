"""Published vectors exercise maintained libraries, not home-grown primitives."""

import json

import pytest
import rfc8785
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey, Ed25519PublicKey

# RFC 8032 section 7.1, tests 1–3. These are PUBLIC TEST SEEDS, never real keys.
# Source and license notice: fixtures/REFERENCE_VECTORS.md.
ED25519 = [
    (
        "9d61b19deffd5a60ba844af492ec2cc44449c5697b326919703bac031cae7f60",
        "d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a",
        "",
        "e5564300c360ac729086e2cc806e828a"
        "84877f1eb8e5d974d873e06522490155"
        "5fb8821590a33bacc61e39701cf9b46b"
        "d25bf5f0595bbe24655141438e7a100b",
    ),
    (
        "4ccd089b28ff96da9db6c346ec114e0f5b8a319f35aba624da8cf6ed4fb8a6fb",
        "3d4017c3e843895a92b70aa74d1b7ebc9c982ccf2ec4968cc0cd55f12af4660c",
        "72",
        "92a009a9f0d4cab8720e820b5f642540a2b27b5416503f8fb3762223ebdb69da085ac1e43e15996e458f3613d0f11d8c387b2eaeb4302aeeb00d291612bb0c00",
    ),
    (
        "c5aa8df43f9f837bedb7442f31dcb7b166d38535076f094b85ce3a2e0b4458f7",
        "fc51cd8e6218a1a38da47ed00230f0580816ed13ba3303ac5deb911548908025",
        "af82",
        "6291d657deec24024827e69c3abe01a30ce548a284743a445e3680d7db5ac3ac18ff9b538d16f290ae67f760984dc6594a7c15e9716ed28dc027beceea1ec40a",
    ),
]


@pytest.mark.parametrize(
    ("seed", "public", "message", "signature"),
    ED25519,
    ids=["rfc8032-test-1", "rfc8032-test-2", "rfc8032-test-3"],
)
def test_rfc8032_known_answers_and_tampering(seed, public, message, signature):
    key = Ed25519PrivateKey.from_private_bytes(bytes.fromhex(seed))
    public_bytes = key.public_key().public_bytes(
        serialization.Encoding.Raw, serialization.PublicFormat.Raw
    )
    assert public_bytes.hex() == public
    payload, expected = bytes.fromhex(message), bytes.fromhex(signature)
    assert key.sign(payload) == expected
    verifier = Ed25519PublicKey.from_public_bytes(bytes.fromhex(public))
    verifier.verify(expected, payload)
    with pytest.raises(InvalidSignature):
        verifier.verify(expected, payload + b"changed")
    with pytest.raises(InvalidSignature):
        verifier.verify(bytes([expected[0] ^ 1]) + expected[1:], payload)
    with pytest.raises(InvalidSignature):
        Ed25519PrivateKey.generate().public_key().verify(expected, payload)


def test_rfc8785_utf16_sorting_known_answer():
    # RFC 8785 section 3.2.3; UTF-8/Python code-point sorting gives a different order.
    value = {
        "\u20ac": "Euro Sign",
        "\r": "Carriage Return",
        "\ufb33": "Hebrew Letter Dalet With Dagesh",
        "1": "One",
        "😀": "Emoji: Grinning Face",
        "\u0080": "Control",
        "ö": "Latin Small Letter O With Diaeresis",
    }
    expected = '{"\\r":"Carriage Return","1":"One","\u0080":"Control","ö":"Latin Small Letter O With Diaeresis","€":"Euro Sign","😀":"Emoji: Grinning Face","דּ":"Hebrew Letter Dalet With Dagesh"}'.encode()
    assert rfc8785.dumps(value) == expected


def test_rfc8785_serialization_known_bytes():
    # RFC 8785 sections 3.2.2 and 3.2.4. Library supports floats; Radar input rejects them.
    value = {
        "numbers": [333333333.33333329, 1e30, 4.50, 2e-3, 1e-27],
        "string": '€$\u000f\nA\'B"\\\\"/',
        "literals": [None, True, False],
    }
    expected = bytes.fromhex(
        "7b226c69746572616c73223a5b6e756c6c2c747275652c66616c73655d2c226e756d62657273223a"
        "5b3333333333333333332e333333333333332c31652b33302c342e352c302e3030322c31652d3237"
        "5d2c22737472696e67223a22e282ac245c75303030665c6e4127425c225c5c5c5c5c222f227d"
    )
    assert rfc8785.dumps(value) == expected
    assert json.loads(expected) == value


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf"), 2**53, "\ud800"])
def test_jcs_library_rejects_non_interoperable_values(bad):
    with pytest.raises(rfc8785.CanonicalizationError):
        rfc8785.dumps({"value": bad})


def test_jcs_preserves_array_order_and_unicode_spelling():
    assert rfc8785.dumps({"x": [2, 1]}) != rfc8785.dumps({"x": [1, 2]})
    assert rfc8785.dumps({"x": "é"}) != rfc8785.dumps({"x": "e\u0301"})
