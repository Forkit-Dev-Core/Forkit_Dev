#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from forkit.schemas import AgentPassport, ModelPassport


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a starter Forkit passport JSON file for a repository."
    )
    parser.add_argument(
        "--passport-type",
        choices=("model", "agent"),
        default="model",
        help="Starter passport type to generate.",
    )
    parser.add_argument(
        "--output",
        default="forkit-passport.json",
        help="Output path for the starter JSON file.",
    )
    parser.add_argument(
        "--name",
        help="Passport name override. Defaults depend on the selected passport type.",
    )
    parser.add_argument(
        "--version",
        default="1.0.0",
        help="Semantic version for the starter passport.",
    )
    parser.add_argument(
        "--creator-name",
        default="Your Team",
        help="Creator name to embed in the starter passport.",
    )
    parser.add_argument(
        "--creator-organization",
        default="Open Source",
        help="Creator organization to embed in the starter passport.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite the output file if it already exists.",
    )
    return parser.parse_args()


def build_model_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "passport_type": "model",
        "name": args.name or "demo-model",
        "version": args.version,
        "creator": {
            "name": args.creator_name,
            "organization": args.creator_organization,
        },
        "description": "Starter ModelPassport template for repository CI validation.",
        "license": "Apache-2.0",
        "status": "active",
        "task_type": "text-generation",
        "architecture": "transformer",
    }
    passport = ModelPassport.from_dict(payload)
    payload["id"] = passport.id
    return payload


def build_agent_payload(args: argparse.Namespace) -> dict[str, Any]:
    payload = {
        "passport_type": "agent",
        "name": args.name or "demo-agent",
        "version": args.version,
        "creator": {
            "name": args.creator_name,
            "organization": args.creator_organization,
        },
        "description": "Starter AgentPassport template for repository CI validation.",
        "license": "Apache-2.0",
        "status": "active",
        "model_id": "0" * 64,
        "task_type": "code-assistant",
        "architecture": "ReAct",
        "role": "assistant",
    }
    passport = AgentPassport.from_dict(payload)
    payload["id"] = passport.id
    return payload


def main() -> int:
    args = parse_args()
    output_path = Path(args.output)

    if output_path.exists() and not args.force:
        print(
            f"Refusing to overwrite existing file: {output_path}. Pass --force to replace it.",
            file=sys.stderr,
        )
        return 1

    if args.passport_type == "model":
        payload = build_model_payload(args)
    else:
        payload = build_agent_payload(args)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")

    print("Forkit passport template generated")
    print(f"  type: {args.passport_type}")
    print(f"  path: {output_path}")
    print(f"  id: {payload['id']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
