# Forkit Dev Core

Deterministic passports, local verification, lineage, and sync contracts for AI models and agents.

[![CI](https://github.com/arpitasarker01/Forkit_Dev/actions/workflows/ci.yml/badge.svg)](https://github.com/arpitasarker01/Forkit_Dev/actions/workflows/ci.yml)
[![Python](https://img.shields.io/badge/python-3.10%2B-2f2a62.svg)](#install)
[![Mode](https://img.shields.io/badge/mode-local--first-008190.svg)](#project-scope)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

## What Forkit Dev Core Is

Forkit Dev Core is the open source, offline-first core of Forkit. It gives a model or agent a portable passport with:

- a deterministic `passport_id`
- local verification that the stored content still matches that identity
- lineage links between models and agents
- local registry, CLI, SDK, CI validation, adapters, and MCP tooling around the same document contract

## Who It Is For

- maintainers who want a portable provenance contract in a public repository
- developers building local or self-hosted model and agent workflows
- teams that need deterministic identity and lineage without adopting a hosted platform

## Why It Is Different

Plain metadata files and plain model cards can describe a system, but they do not by themselves define a deterministic identity contract, local tamper detection, or lineage-aware tooling.

Forkit stays file-based and local, but adds:

- deterministic identity derived from defined passport fields
- verification and tamper detection you can run locally or in CI
- lineage and sync contracts for derived models and agents
- local SDK, CLI, server, adapters, and MCP access to the same passport format

See [`docs/comparisons.md`](docs/comparisons.md) for a deeper, factual comparison.

## First Success

Install the package from a local checkout and run the smallest example:

```bash
git clone https://github.com/arpitasarker01/Forkit_Dev.git
cd Forkit_Dev
pip install -e .
python examples/minimal_local_passport.py
```

Expected output:

```json
{
  "model_id": "886313312d44d89fc36cc9e3ec40a50017a8375ef193574b1c55c4519f090f82",
  "passport_type": "model",
  "name": "hello-local-model",
  "valid": true,
  "models": 1,
  "agents": 0
}
```

## Choose Your Path

| Path | Install | Run | Outcome |
|---|---|---|---|
| Local SDK quickstart | `pip install -e .` | `python examples/minimal_local_passport.py` | Create and verify one local model passport |
| CLI quickstart | `pip install -e ".[cli]"` | `python examples/cli_quickstart.py` | Exercise real CLI registration, listing, verification, and stats |
| GitHub CI validation | `pip install -e .` | `python examples/github_ci_quickstart.py` | Generate and validate a starter passport for CI |
| MCP quickstart | `pip install -e ".[mcp]"` | `python examples/mcp_quickstart.py` | Exercise the local MCP tool surface and draft behavior |

## Architecture Flow

Write a passport document -> derive a deterministic `passport_id` -> store it locally in JSON plus a rebuildable SQLite index -> verify it locally or in CI -> inspect lineage -> optionally export or sync through local HTTP contracts or a local MCP server.

## Install

PyPI publishing is prepared but not live yet. Until the first release is published, install from GitHub or a local checkout:

```bash
git clone https://github.com/arpitasarker01/Forkit_Dev.git
cd Forkit_Dev
pip install -e .
```

Optional extras:

```bash
pip install -e ".[cli]"        # Typer CLI
pip install -e ".[mcp]"        # local MCP server
pip install -e ".[pydantic]"   # Pydantic v2 backend
pip install -e ".[server]"     # local FastAPI service
pip install -e ".[langchain]"  # LangChain adapter helpers
pip install -e ".[langgraph]"  # LangGraph adapter helpers
pip install -e ".[postgres]"   # Postgres-backed sync receiver
pip install -e ".[all]"        # everything optional
pip install -e ".[dev]"        # development and test dependencies
```

Canonical imports use `forkit.*`. The legacy `forkit_core.*` namespace remains available as a compatibility shim.

## Runnable Examples

### Local SDK quickstart

```bash
python examples/minimal_local_passport.py
```

Expected output:

```json
{
  "model_id": "886313312d44d89fc36cc9e3ec40a50017a8375ef193574b1c55c4519f090f82",
  "passport_type": "model",
  "name": "hello-local-model",
  "valid": true,
  "models": 1,
  "agents": 0
}
```

### CLI quickstart

```bash
pip install -e ".[cli]"
python examples/cli_quickstart.py
```

Expected output:

```json
{
  "registered_model_id": "2d0902a97ef8448849e5edd83157e1d6faca0fb785ba12b3f9225b86542e109a",
  "list_contains_model": true,
  "verify_valid": true,
  "stats": {
    "models": 1,
    "agents": 0
  }
}
```

If you want the raw CLI commands instead of the smoke example:

```bash
forkit register model examples/register_model.yaml --registry-root /tmp/forkit-cli-demo
forkit list --registry-root /tmp/forkit-cli-demo
forkit stats --registry-root /tmp/forkit-cli-demo
```

### GitHub CI quickstart

```bash
python examples/github_ci_quickstart.py
```

Expected output:

```json
{
  "generated": true,
  "validated": true,
  "passport_path": "forkit-passport.json",
  "validator_summary": "Forkit passport is valid"
}
```

Copyable demo files live under [`publish/github-ci-demo/`](publish/github-ci-demo/), including a ready-to-copy workflow at [`publish/github-ci-demo/.github/workflows/validate-forkit-passport.yml`](publish/github-ci-demo/.github/workflows/validate-forkit-passport.yml).

### MCP quickstart

```bash
pip install -e ".[mcp]"
python examples/mcp_quickstart.py
```

Expected output:

```json
{
  "search_results": 2,
  "passport_name": "mcp-demo-model",
  "verify_valid": true,
  "ancestor_count": 1,
  "draft_passport_id": "2769eee050f2eceee1a82c13b6b1317370e1449801eb6ac955a1d4ab3b61e171"
}
```

To run the actual stdio server:

```bash
forkit-mcp --registry-root /tmp/forkit-mcp-registry
```

If you also install `.[cli]`, you can use the CLI alias:

```bash
forkit mcp serve --registry-root /tmp/forkit-mcp-registry
```

See [`docs/mcp.md`](docs/mcp.md) for install details, client configuration, and the tool list.

### Tamper detection demo

```bash
python examples/tamper_detection_demo.py
```

Expected output:

```json
{
  "stored_id": "8a267a56d35d2703b39c73efafddb9b8e8e070702f43f2166af8cd2c67ad4353",
  "valid_before": true,
  "valid_after": false,
  "reason_after": "id_mismatch",
  "derived_after": "748af1fe44ebd65918850d8a9ff584462f4cfc7b8577f37bf060210b9a0736b0"
}
```

## Local Surfaces

- SDK: `forkit.sdk.ForkitClient`
- CLI: `forkit ...`
- Local HTTP service: `forkit serve --host 127.0.0.1 --port 8000`
- Local MCP server: `forkit-mcp --registry-root ~/.forkit/registry`
- GitHub passport validation action: [`.github/actions/validate-passport/action.yml`](.github/actions/validate-passport/action.yml)

## Project Scope

This repository is intentionally limited to the open source core.

Included:

- deterministic passport schemas and identity derivation
- local JSON and SQLite registry behavior
- lineage, integrity verification, and tamper detection
- local HTTP sync and export contracts
- LangChain, LangGraph, OpenClaw, and local MCP adapter surfaces
- developer tooling, examples, and CI validation

Not included:

- hosted dashboards
- hosted auth
- enterprise-only approval flows
- SaaS product behavior

## Development

```bash
pip install -e ".[dev]"
pytest
python -m build
```

Useful docs:

- [`CONTRIBUTING.md`](CONTRIBUTING.md)
- [`SECURITY.md`](SECURITY.md)
- [`docs/mcp.md`](docs/mcp.md)
- [`docs/comparisons.md`](docs/comparisons.md)
- [`docs/release-checklist.md`](docs/release-checklist.md)
- [`docs/identity-spec.md`](docs/identity-spec.md)
