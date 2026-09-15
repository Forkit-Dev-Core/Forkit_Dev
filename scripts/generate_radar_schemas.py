"""Export the installed Radar models' JSON shape schemas; no remote references."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from forkit_radar.contracts import CONTRACTS


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parents[1] / "packages/radar/src/forkit_radar/schemas"
    destination.mkdir(parents=True, exist_ok=True)
    different = []
    for name, model in CONTRACTS.items():
        path = destination / f"{name}-v1.json"
        content = json.dumps(model.model_json_schema(by_alias=True), indent=2) + "\n"
        if args.check:
            if not path.exists() or path.read_text() != content:
                different.append(name)
        else:
            path.write_text(content)
    expected = {f"{name}-v1.json" for name in CONTRACTS}
    if args.check and {p.name for p in destination.glob("*.json")} != expected:
        different.append("unexpected-schema-file")
    if different:
        print("Schema drift: " + ", ".join(different))
        return 1
    print(f"{len(CONTRACTS)} schemas {'checked' if args.check else 'written'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
