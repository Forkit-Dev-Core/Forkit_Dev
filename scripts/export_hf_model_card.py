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

from forkit.domain.integrity import verify_passport_id
from forkit.schemas import ModelPassport

PIPELINE_TAG_MAP = {
    "code-completion": "text-generation",
    "code-generation": "text-generation",
    "embedding": "feature-extraction",
    "function-calling": "text-generation",
    "image-captioning": "image-to-text",
    "image-classification": "image-classification",
    "image-generation": "text-to-image",
    "instruction-following": "text-generation",
    "named-entity-recognition": "token-classification",
    "question-answering": "question-answering",
    "reasoning": "text-generation",
    "reranking": "feature-extraction",
    "sentiment-analysis": "text-classification",
    "speech-to-text": "automatic-speech-recognition",
    "text-classification": "text-classification",
    "text-generation": "text-generation",
    "text-summarization": "summarization",
    "text-to-speech": "text-to-speech",
    "translation": "translation",
    "visual-question-answering": "visual-question-answering",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export a Forkit ModelPassport JSON file to a Hugging Face-style model card."
    )
    parser.add_argument(
        "--path",
        default="forkit-passport.json",
        help="Path to the source Forkit passport JSON file. Defaults to forkit-passport.json.",
    )
    parser.add_argument(
        "--output",
        help="Output markdown path. Defaults to <passport-stem>.hf-model-card.md next to the source.",
    )
    return parser.parse_args()


def load_passport(path: Path) -> tuple[dict[str, Any], ModelPassport]:
    if not path.is_file():
        raise FileNotFoundError(f"Passport file not found: {path}")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON at line {exc.lineno}, column {exc.colno}: {exc.msg}"
        ) from exc

    if not isinstance(payload, dict):
        raise ValueError("Passport file must contain one top-level JSON object.")

    if payload.get("passport_type") != "model":
        raise ValueError(
            "This first Hugging Face bridge only exports ModelPassport files. "
            f"Got passport_type={payload.get('passport_type')!r}."
        )

    try:
        passport = ModelPassport.from_dict(payload)
    except Exception as exc:  # noqa: BLE001 - keep schema errors visible to developers
        raise ValueError(str(exc)) from exc

    result = verify_passport_id(payload)
    if not result["valid"]:
        reason = result["reason"]
        if reason == "missing_id":
            raise ValueError(
                "Passport is missing `id`. Export requires a committed deterministic ID."
            )
        raise ValueError(
            "Passport `id` does not match the deterministic ID derived from its content. "
            f"stored={result['stored_id']} derived={result['derived_id']}"
        )

    return payload, passport


def default_output_path(source_path: Path) -> Path:
    base = source_path.with_suffix("")
    return base.with_name(f"{base.name}.hf-model-card.md")


def creator_label(passport: ModelPassport) -> str:
    creator = passport.creator
    if getattr(creator, "organization", None):
        return f"{creator.name} ({creator.organization})"
    return creator.name


def maybe_value(value: Any) -> Any:
    if value in (None, "", [], {}):
        return None
    return value


def compact(value: Any) -> Any:
    if isinstance(value, dict):
        pruned: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = compact(item)
            if cleaned not in (None, "", [], {}):
                pruned[key] = cleaned
        return pruned or None
    if isinstance(value, list):
        pruned_list = [compact(item) for item in value]
        pruned_list = [item for item in pruned_list if item not in (None, "", [], {})]
        return pruned_list or None
    return maybe_value(value)


def scalar_to_yaml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    return json.dumps(str(value))


def to_yaml(value: Any, indent: int = 0) -> str:
    prefix = " " * indent
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            if isinstance(item, dict):
                lines.append(f"{prefix}{key}:")
                lines.append(to_yaml(item, indent + 2))
            elif isinstance(item, list):
                if not item:
                    lines.append(f"{prefix}{key}: []")
                else:
                    lines.append(f"{prefix}{key}:")
                    for entry in item:
                        lines.append(f"{prefix}  - {scalar_to_yaml(entry)}")
            else:
                lines.append(f"{prefix}{key}: {scalar_to_yaml(item)}")
        return "\n".join(lines)
    raise TypeError("to_yaml expects a dict at the root.")


def pipeline_tag_for(task_type: str) -> str | None:
    return PIPELINE_TAG_MAP.get(task_type)


def build_front_matter(passport: ModelPassport, source_path: Path) -> str:
    task_type = str(passport.task_type.value if hasattr(passport.task_type, "value") else passport.task_type)
    architecture = str(
        passport.architecture.value if hasattr(passport.architecture, "value") else passport.architecture
    )
    license_value = str(passport.license.value if hasattr(passport.license, "value") else passport.license)
    tags = [
        "forkit-core",
        "model-passport",
        "deterministic-id",
        f"task:{task_type}",
        f"architecture:{architecture}",
    ]
    if passport.base_model_id or passport.parent_hash:
        tags.append("lineage-ready")
    if passport.artifact_hash:
        tags.append("artifact-hash")
    if getattr(passport.capabilities, "supports_function_calling", False):
        tags.append("function-calling")

    metadata = compact(
        {
            "license": None if license_value == "other" else license_value,
            "pipeline_tag": pipeline_tag_for(task_type),
            "language": getattr(passport.capabilities, "languages", None),
            "base_model": passport.base_model_name,
            "tags": tags,
            "forkit": {
                "passport_id": passport.id,
                "passport_type": passport.passport_type,
                "source_passport": source_path.as_posix(),
                "deterministic_id_verified": True,
                "task_type": task_type,
                "architecture": architecture,
                "artifact_hash": passport.artifact_hash,
                "parent_hash": passport.parent_hash,
                "base_model_id": passport.base_model_id,
                "external_model_id": passport.model_id,
            },
        }
    )

    return f"---\n{to_yaml(metadata)}\n---"


def bullet(label: str, value: str | None) -> str:
    if not value:
        return f"- {label}: Not recorded"
    return f"- {label}: {value}"


def code_value(value: str | None) -> str | None:
    if not value:
        return None
    return f"`{value}`"


def build_body(passport: ModelPassport, source_path: Path) -> str:
    description = passport.description or (
        "Forkit ModelPassport exported into a Hugging Face-friendly card format."
    )
    task_type = str(passport.task_type.value if hasattr(passport.task_type, "value") else passport.task_type)
    architecture = str(
        passport.architecture.value if hasattr(passport.architecture, "value") else passport.architecture
    )
    license_value = str(passport.license.value if hasattr(passport.license, "value") else passport.license)
    lines = [
        f"# {passport.name}",
        "",
        description,
        "",
        "## Forkit Passport Summary",
        "",
        bullet("Passport ID", code_value(passport.id)),
        bullet("Version", f"`{passport.version}`"),
        bullet("Creator", creator_label(passport)),
        bullet("Task type", f"`{task_type}`"),
        bullet("Architecture", f"`{architecture}`"),
        bullet("License", f"`{license_value}`"),
        "",
        "## Provenance and Verification",
        "",
        "This model card was exported from a Forkit `ModelPassport`. "
        "Hugging Face model cards describe the model for distribution and discovery, "
        "while Forkit passports add deterministic identity, SHA-256-ready provenance fields, "
        "and lineage-aware verification metadata.",
        "",
        bullet("Source passport", f"`{source_path.as_posix()}`"),
        bullet("Deterministic passport ID", code_value(passport.id)),
        bullet("Artifact hash", code_value(passport.artifact_hash)),
        bullet("Parent artifact hash", code_value(passport.parent_hash)),
        bullet("Base model passport ID", code_value(passport.base_model_id)),
    ]

    if passport.base_model_name:
        lines.append(bullet("Base model name", passport.base_model_name))
    if passport.model_id:
        lines.append(bullet("External model identifier", f"`{passport.model_id}`"))

    if passport.training_data:
        lines.extend(
            [
                "",
                "## Training Data References",
                "",
            ]
        )
        for entry in passport.training_data:
            lines.append(f"- {entry.name}")

    return "\n".join(lines) + "\n"


def main() -> int:
    args = parse_args()
    source_path = Path(args.path)

    try:
        _, passport = load_passport(source_path)
    except (FileNotFoundError, ValueError) as exc:
        print(f"Forkit Hugging Face export failed: {exc}", file=sys.stderr)
        return 1

    output_path = Path(args.output) if args.output else default_output_path(source_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    content = "\n\n".join(
        [
            build_front_matter(passport, source_path),
            build_body(passport, source_path),
        ]
    )
    output_path.write_text(content, encoding="utf-8")

    print("Forkit Hugging Face model card exported")
    print(f"  source: {source_path}")
    print(f"  output: {output_path}")
    print(f"  passport_id: {passport.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
