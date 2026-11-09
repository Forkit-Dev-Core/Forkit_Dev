"""Check the portable v1 fixtures against the Core reference implementation."""

import hashlib
import json
from pathlib import Path

import pytest

from forkit.domain.identity import compute_id
from forkit.domain.integrity import verify_passport_id
from forkit.domain.lineage import LineageGraph

VECTORS = json.loads((Path(__file__).parent / "fixtures" / "passport-v1.json").read_text("utf-8"))


@pytest.mark.parametrize("vector", VECTORS["identity"], ids=lambda vector: vector["name"])
def test_passport_v1_identity(vector):
    passport = vector["passport"]
    creator = passport["creator"]
    expected = vector["expected_id"]

    assert hashlib.sha256(vector["payload"].encode("utf-8")).hexdigest() == expected
    assert compute_id(
        passport["passport_type"],
        passport["name"],
        passport["version"],
        creator["name"],
        creator.get("organization"),
        passport.get("artifact_hash"),
    ) == expected
    assert verify_passport_id({**passport, "id": expected})["valid"]
    assert verify_passport_id({**passport, "id": expected, "name": "Altered name"})["reason"] == (
        "id_mismatch"
    )
    assert verify_passport_id(passport)["reason"] == "missing_id"


def test_passport_v1_lineage(tmp_path):
    vector = VECTORS["lineage"]
    path = tmp_path / "lineage.json"
    path.write_text(json.dumps(vector["graph"]), encoding="utf-8")
    graph = LineageGraph.load(path)

    assert graph.to_dict() == vector["graph"]
    query = vector["query"]
    assert {node.id for node in graph.ancestors(query["id"])} == set(query["ancestors"])
    assert {node.id for node in graph.descendants(query["id"])} == set(query["descendants"])
