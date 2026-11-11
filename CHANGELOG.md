# Changelog

All notable changes to `forkit-core` will be documented here.

Format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
This project uses [Semantic Versioning](https://semver.org/).

---

## [Unreleased]

### Fixed

- Reject cycles, missing endpoints, and unknown edge types when loading lineage
  JSON, while preserving saved edge timestamps. Fixes #16.

---

## [0.1.0] — 2026-03-16

Initial public release.

### Added

**Core domain (`forkit.domain`)**
- `identity.py` — `compute_id`, `validate_hash`, `validate_version`, `to_json_safe`. Canonical, offline-first passport ID derivation via SHA-256.
- `hashing.py` — `HashEngine` with `hash_file`, `hash_directory`, `hash_dict`, `hash_string`, `hash_bytes`, `hash_artifact`, `hash_config`, `hash_system_prompt`, `hash_metadata`; corresponding `verify_*` methods; strict `is_valid_hash`.
- `lineage.py` — `LineageGraph` DAG with DFS cycle detection, `ancestors`, `descendants`, `edges_for`, `nodes_by_type`; `register_model` / `register_agent` convenience constructors; JSON save/load.
- `integrity.py` — `verify_passport_id`, `compute_metadata_hash`.

**Schemas (`forkit.schemas`)**
- `ModelPassport` — identity and provenance document for an AI model. Fields include `artifact_hash`, `parent_hash`, `base_model_id`, `base_model_name`, `fine_tuning_method`, `training_data`, `capabilities`, `parameter_count`.
- `AgentPassport` — identity and provenance document for an AI agent. Fields include `model_id` (hard link to `ModelPassport`), `system_prompt`, `tools`, `parent_agent_id`, `endpoint_hash`, `fork_reason`.
- Auto-selects Pydantic v2 backend when available; falls back to pure-Python dataclasses (zero hard dependencies).
- Shared Pydantic inner models extracted to `pydantic/_types.py` — no duplication between model and agent backends.
- Full `to_dict` / `from_dict` serialisation roundtrip with enum and datetime coercion.
- `_PYDANTIC_AVAILABLE` flag exported from `forkit.schemas`.

**Registry (`forkit.registry`)**
- `LocalRegistry` — filesystem-backed store (JSON files + SQLite index).
- `register_model`, `register_agent`, `get`, `delete`, `list`, `search`, `stats`, `verify_passport`.
- SQLite index is always rebuildable from JSON via `rebuild_index()`.

**SDK (`forkit.sdk`)**
- `ForkitClient` — `client.models`, `client.agents`, `client.lineage`, `client.verify`.

**CLI (`forkit.cli`)**
- `forkit register model/agent <yaml>` — register from YAML file.
- `forkit inspect <id>` — print full passport JSON.
- `forkit list [--type model|agent] [--status draft|active|...]`
- `forkit search <query>`
- `forkit lineage <id>` — print ancestor / descendant tree.
- `forkit verify <id>` — integrity verification.
- `forkit stats` — registry summary.

**Examples and tests**
- `examples/use_cases.py` — standalone runnable demo for all 10 use cases.
- `tests/test_use_cases.py` — pytest test suite (39 assertions, 10 test classes).
- `tests/conftest.py` — shared fixtures.

**Documentation**
- `docs/identity-spec.md` — formal specification of the passport identity contract, hash-chain provenance model, serialisation guarantees, and regression anchors.

### Design decisions

- **Offline-first** — all identity and integrity operations work without a network connection or a running server.
- **Hash-chain provenance** — `artifact_hash` (content fingerprint) + `parent_hash` (lineage link) form a verifiable chain without PKI or central authority.
- **Dual backend, one interface** — dataclass backend has zero external dependencies; install `pydantic>=2` for JSON Schema generation and `.model_validate()` / `.model_dump()` support.
- **SQLite as a rebuildable index** — JSON files are the source of truth; SQLite is a query convenience, not the store of record.

---

[Unreleased]: https://github.com/Forkit-Dev-Core/Forkit_Dev/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Forkit-Dev-Core/Forkit_Dev/releases/tag/v0.1.0
