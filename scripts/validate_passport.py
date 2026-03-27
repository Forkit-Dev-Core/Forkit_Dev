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

from forkit.domain.identity import validate_hash
from forkit.domain.integrity import verify_passport_id
from forkit.schemas import AgentPassport, ModelPassport

PASSPORT_TYPES = {
    "agent": AgentPassport,
    "model": ModelPassport,
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate a Forkit passport JSON file for local use or GitHub Actions."
    )
    parser.add_argument(
        "--path",
        default="forkit-passport.json",
        help="Path to the passport JSON file. Defaults to forkit-passport.json.",
    )
    return parser.parse_args()


def github_error(path: Path, message: str) -> None:
    print(f"::error file={path.as_posix()}::{message}", file=sys.stderr)


def github_notice(path: Path, message: str) -> None:
    print(f"::notice file={path.as_posix()}::{message}")


def load_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(
            f"Passport file not found at {path}. Configure --path or add the file to your repo."
        )

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("Passport file must contain one top-level JSON object.")

    return payload


def instantiate_passport(payload: dict[str, Any]) -> ModelPassport | AgentPassport:
    passport_type = payload.get("passport_type")
    if passport_type not in PASSPORT_TYPES:
        allowed = ", ".join(sorted(PASSPORT_TYPES))
        raise ValueError(
            f"`passport_type` must be one of: {allowed}. Got: {passport_type!r}"
        )

    try:
        passport = PASSPORT_TYPES[passport_type].from_dict(payload)
    except Exception as exc:  # noqa: BLE001 - surface schema errors verbatim for CI users
        raise ValueError(str(exc)) from exc

    return passport


def validate_structural_fields(payload: dict[str, Any]) -> None:
    if payload.get("passport_type") == "agent":
        try:
            validate_hash(payload.get("model_id"))
        except ValueError as exc:
            raise ValueError(
                "AgentPassport `model_id` must be a 64-char Forkit passport ID hash."
            ) from exc


def validate_id(path: Path, payload: dict[str, Any], derived_id: str) -> None:
    stored_id = payload.get("id")
    if not stored_id:
        raise ValueError(
            "Passport is missing `id`. Commit the deterministic ID to the file so CI can verify "
            f"integrity. Expected id: {derived_id}"
        )

    try:
        validate_hash(stored_id)
    except ValueError as exc:
        raise ValueError(
            "Passport `id` must be a 64-char SHA-256 hex digest."
        ) from exc

    result = verify_passport_id(payload)
    if not result["valid"]:
        raise ValueError(
            "Passport `id` does not match the schema-derived deterministic ID. "
            f"stored={result['stored_id']} derived={result['derived_id']}"
        )

    github_notice(path, f"Deterministic id verified: {stored_id}")


def main() -> int:
    args = parse_args()
    path = Path(args.path)

    try:
        payload = load_json(path)
        passport = instantiate_passport(payload)
        validate_structural_fields(payload)
        validate_id(path, payload, passport.id)
    except (FileNotFoundError, ValueError) as exc:
        github_error(path, str(exc))
        print(f"Forkit passport validation failed for {path}", file=sys.stderr)
        print(f"- {exc}", file=sys.stderr)
        return 1

    print("Forkit passport is valid")
    print(f"  path: {path}")
    print(f"  type: {passport.passport_type}")
    print(f"  name: {passport.name}")
    print(f"  version: {passport.version}")
    print(f"  id: {passport.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
