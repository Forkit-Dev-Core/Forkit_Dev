# forkit-core

**Open-source AI passports with deterministic IDs and lineage.**

Portable passports for AI models and agents: deterministic IDs, provenance links, artifact hashes, lineage records, and CI-friendly validation.

## Try it in 30 seconds

```bash
git clone https://github.com/Forkit-Dev-Core/Forkit_Dev.git
cd Forkit_Dev
pip install -e .

python examples/deterministic_identity_demo.py
```

Want the CLI flow instead?

```bash
pip install -e ".[cli]"
python scripts/generate_passport_template.py --passport-type model --output forkit-passport.json
python scripts/validate_passport.py --path forkit-passport.json
```

Create a passport locally. Verify it in GitHub CI. Keep the identity portable. Connect it to Forkit.dev later when you need hosted visibility or governance workflows.

AI models and agents often move across repos, tools, teams, and runtimes without stable identity, lineage, or verification. `forkit-core` gives them a local-first identity layer you can create, validate, and keep portable.

Questions, launch feedback, or contributor interest: open a GitHub issue or join the Discord / Slack links in the [Community](#community) section.

[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-2f2a62.svg)](#install)
[![Status](https://img.shields.io/badge/status-alpha-f49355.svg)](#current-status)
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-008190.svg)](#contributing)

![forkit-core passport flow](./docs/assets/forkit-passport-flow.png)

That quick start shows the core property:

- same stable passport inputs => same deterministic `passport_id`
- changed artifact or creator => different `passport_id`

Example output:

```text
Forkit deterministic passport demo

same input               ddfd461f5fc78574c3244da346f64bf3b1d95e83e0dfe174209937f9d561bd0b
same input again         ddfd461f5fc78574c3244da346f64bf3b1d95e83e0dfe174209937f9d561bd0b
changed artifact         e271004e8f9e83d9e81f8f5d3d35736c4e4bf841d46d821d74b59e439d6f3cea
changed creator          f78fb6bf1d7feee0fb2020753904b50a550f194a5f5664dff91b70601e31f0ac
```

The CLI flow above creates a starter `ModelPassport`, writes a deterministic `id` into `forkit-passport.json`, and verifies that the stored `id` still matches the schema-derived identity. No hosted service is required.

## Why This Exists

`forkit-core` makes the passport itself the durable boundary for AI identity.
Instead of depending on one registry, one dashboard, or one runtime, you keep a
portable document that can be created locally, reviewed in Git, validated in
CI, synced across environments, and re-verified later without changing its
identity.

This repository is for teams that want:

- deterministic `passport_id` derivation for models and agents
- provenance links and artifact hashes that stay attached to the passport
- lineage across base models, fine-tunes, and agents
- local-first workflows that do not require a hosted control plane
- a verification path that fits normal repository and CI practices

## What This Is And Isn't

What it is:

- a deterministic identity contract for AI models and agents
- a portable passport document with provenance, artifact hashes, and lineage
- a local-first SDK, CLI, registry, and CI validation path

What it is not:

- a claim that the model is safe, legal, or approved
- a hosted team governance product by itself
- a replacement for model cards, SBOMs, or attestations

`forkit-core` is meant to complement those artifacts by giving the model or agent
itself a stable portable identity that other review and governance layers can
join on.

## Common Questions

**Why not just use model cards?**

Model cards are useful documentation, but they are not deterministic identity.
`forkit-core` gives the passport a rebuildable `passport_id` that can be
re-derived and verified locally.

**Why not just use attestations or SBOMs?**

Attestations and SBOMs are important evidence formats. `forkit-core` is the
identity layer they can attach to. It focuses on stable identity, lineage, and
portable provenance rather than replacing supply-chain evidence standards.

**Does `forkit-core` verify that a claim is true?**

No. It verifies that a passport's deterministic identity still matches its
declared contents. Truth, ownership, and publication claims still require
source proof, review, or hosted governance workflows.

## Current Scope

- Deterministic `ModelPassport` and `AgentPassport` records
- Local JSON passports with a rebuildable SQLite index
- Python SDK, CLI, validation scripts, and local HTTP service
- GitHub CI validation for committed passport files
- Framework adapters for LangGraph, LangChain, and OpenClaw
- File-based Hugging Face model card export
- A prototype browser UI under [`web/`](./web), clearly separate from any hosted control plane

Current maturity:

- Alpha open-source core, but the identity contract and deterministic verification behavior are already stable enough to evaluate seriously
- PyPI is not live yet
- advanced flows such as hosted import preparation, self-host sync, adapters, and the prototype UI exist, but they are not the primary first-use path

Public install path:

```bash
pip install "forkit-core @ git+https://github.com/Forkit-Dev-Core/Forkit_Dev.git"
```

## Primary and Advanced Paths

| Goal | Maturity | Entry point |
|---|---|
| Deterministic identity demo | Primary | `python examples/deterministic_identity_demo.py` |
| Smallest end-to-end local registration flow | Primary | `python examples/sdk_quickstart.py` |
| Register from YAML through the CLI | Primary | `forkit register model examples/register_model.yaml` |
| Validate a committed passport in CI | Primary | [`publish/github-ci-demo/`](./publish/github-ci-demo/) |
| Run the local HTTP service | Primary | `pip install -e ".[server]" && forkit serve --host 127.0.0.1 --port 8000` |
| Try self-host sync between two local registries | Advanced | `python examples/self_host_sync_quickstart.py` |
| Try the LangGraph adapter | Advanced | `python examples/langgraph_sync_quickstart.py` |
| Try the LangChain adapter | Advanced | `python examples/langchain_sync_quickstart.py` |
| Try the OpenClaw adapter | Advanced | `python examples/openclaw_quickstart.py` |
| Explore the browser UI prototype | Early | `cd web && npm install && npm run dev` |

## `forkit-core` and Forkit.dev

`forkit-core` is the local-first open-source foundation in this repository:
schemas, deterministic IDs, artifact hashing, lineage, local registry, SDK,
CLI, sync primitives, optional local service, adapters, and the prototype web
UI.

`Forkit.dev` is the broader hosted direction around that core for teams that
prefer browser-based passport creation, dashboards, private workspaces,
telemetry, collaboration, approvals, and governance workflows. Those hosted
workflows are not implemented in this repository today.

## Identity Boundary

`forkit-core` uses the deterministic `passport_id` as the canonical
portable identity for a passport.

If a passport is later published or connected to a hosted Forkit deployment,
the hosted system must preserve that `passport_id` and attach any hosted or
public identity as additional application metadata. Hosted layers may join on
`passport_id`, but they must not rewrite it.

This repository does not implement a hosted account, claim, or publish flow
today. It implements the local identity contract that those future workflows
must respect.

## Install

Python 3.10+ is required. Node.js 20.19+ is only needed if you want to run the
frontend prototype.

Install from this repository:

```bash
git clone https://github.com/Forkit-Dev-Core/Forkit_Dev.git
cd Forkit_Dev
pip install -e .
```

Optional extras:

```bash
pip install -e ".[pydantic]"   # Pydantic v2 backend + JSON Schema
pip install -e ".[cli]"        # Typer CLI + YAML input
pip install -e ".[langchain]"  # LangChain adapter helpers
pip install -e ".[langgraph]"  # LangGraph adapter helpers
pip install -e ".[server]"     # FastAPI + Uvicorn local service
pip install -e ".[postgres]"   # Postgres-backed sync receiver
pip install -e ".[all]"        # all optional extras
pip install -e ".[dev]"        # tests, linting, and development tooling
```

Python imports should use `forkit.*`. The legacy `forkit_core.*` namespace is
kept as a compatibility shim in `v0.1.x`.

## Core Concepts

- `passport_id`: deterministic SHA-256 identity derived from stable passport fields
- `artifact_hash`: content fingerprint for a model artifact, agent bundle, or config material
- `parent_hash`: hash-chain link to the parent artifact in a lineage
- `base_model_id` and `parent_agent_id`: passport-ID lineage links for fine-tunes and forks
- local registry: JSON source of truth with a rebuildable SQLite index
- sync bridge: generic `GET /export` and `POST /sync/passports` contract that does not rewrite identity

For the full identity contract, hash rules, regression anchors, and
serialization guarantees, see [`docs/identity-spec.md`](./docs/identity-spec.md).

## What's Inside

| Module | Purpose |
|---|---|
| `forkit/` | Core package: domain logic, schemas, registry, SDK, server, and sync |
| `forkit_core/` | Compatibility namespace kept during the `v0.1.x` transition |
| `forkit_langgraph/` | LangGraph adapter helpers |
| `forkit_langchain/` | LangChain adapter helpers |
| `forkit_openclaw/` | OpenClaw adapter |
| `examples/` | Runnable quickstarts and sample passports |
| `publish/` | Copyable GitHub CI and publishing demos |
| `scripts/` | Validation, export, and template utilities |
| `web/` | React + TypeScript + Vite prototype UI |
| `docs/` | Identity specification and image assets |
| `tests/` | Regression coverage for schemas, registry, server, sync, and adapters |

## GitHub CI Validation

`forkit-core` includes a lightweight GitHub-native validation path for a
committed passport file. It checks that the file exists, validates the JSON
against the current `ModelPassport` or `AgentPassport` schema, and verifies
that the stored deterministic `id` matches the file content.

Start with [`publish/github-ci-demo/`](./publish/github-ci-demo/):

1. Copy [`publish/github-ci-demo/forkit-passport.json`](./publish/github-ci-demo/forkit-passport.json) into your repository root.
2. Copy the sample workflow from [`publish/github-ci-demo/README.md`](./publish/github-ci-demo/README.md) or the local reusable action shown below.
3. Push or open a pull request.
4. GitHub Actions will fail on missing files, invalid JSON, schema errors, or deterministic `id` mismatches.

Minimal workflow:

```yaml
name: Validate Forkit passport

on:
  pull_request:
    paths:
      - "forkit-passport.json"
      - ".github/workflows/validate-forkit-passport.yml"
  push:
    branches:
      - main
    paths:
      - "forkit-passport.json"
      - ".github/workflows/validate-forkit-passport.yml"

jobs:
  validate-passport:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: Forkit-Dev-Core/Forkit_Dev/.github/actions/validate-passport@main
        with:
          passport-path: forkit-passport.json
```

Run the same check locally:

```bash
python scripts/validate_passport.py --path forkit-passport.json
```

This repository's own workflow validates
[`examples/forkit-passport.model.json`](./examples/forkit-passport.model.json).

## Python SDK

```python
from forkit.sdk import ForkitClient

client = ForkitClient()  # defaults to ~/.forkit/registry

model_id = client.models.register(
    name="my-model",
    version="1.0.0",
    task_type="text-generation",
    architecture="transformer",
    creator={"name": "Your Team", "organization": "Open Source"},
)

agent_id = client.agents.register(
    name="support-agent",
    version="1.0.0",
    model_id=model_id,
    task_type="customer-support",
    architecture="ReAct",
    creator={"name": "Your Team", "organization": "Open Source"},
    system_prompt="Answer concisely.",
)

print(client.lineage.ancestors(agent_id))
print(client.verify(model_id))
```

Runnable entry point:

```bash
python examples/sdk_quickstart.py
```

## CLI

Install the CLI extra first:

```bash
pip install -e ".[cli]"
```

If `forkit` is not on your `PATH`, use `python -m forkit.cli.main ...` with
the same arguments.

Repository and package branding uses `forkit-core`. The local CLI binary stays
`forkit` intentionally so the user-facing command remains short and stable.

Common commands:

```bash
forkit register model examples/register_model.yaml
forkit register agent examples/register_agent.yaml

forkit inspect <passport-id>
forkit list --type model --status active
forkit search "llama"
forkit lineage <passport-id>
forkit verify <passport-id>
forkit hosted-proof <passport-id>
forkit stats

forkit sync status
forkit sync push https://example.com/sync/passports --target main-server
forkit sync pull https://example.com/export --source remote-dev
```

The CLI is local-first. `forkit sync push` and `forkit sync pull` are generic
sync primitives for self-hosted or custom HTTP endpoints that preserve
`passport_id`. They are not a hosted Forkit publish or claim flow.

`examples/register_model.yaml` is runnable as checked in. `examples/register_agent.yaml`
is a second-step sample and expects an already registered model passport ID in `model_id`.

When you want to bind an OSS passport into hosted Forkit later, first register
or create the passport locally, then run `forkit hosted-proof <passport-id>`.
That command looks up the passport in your local registry and
prints the exact `/.well-known/forkit-verify.txt` proof line and target URL for
supported GitHub, Hugging Face, and GitLab sources.

## Local Service and Sync

Install the server extra and run the local HTTP service over the same
filesystem-backed registry:

```bash
pip install -e ".[server]"
forkit serve --host 127.0.0.1 --port 8000
```

Relevant routes:

- `GET /` for service info
- `GET /healthz` and `GET /readyz` for liveness/readiness checks
- `POST /models` and `POST /agents` for passport registration
- `GET /passports/{id}` and `POST /verify/{id}` for fetch and verification
- `GET /lineage/{id}` for ancestry and descendants
- `GET /export` and `POST /sync/passports` for generic sync

Security posture for the local service:

- keep `forkit serve` on `127.0.0.1` unless you intentionally place it behind a trusted network boundary
- set `FORKIT_SYNC_BEARER_TOKEN` before exposing `POST /sync/passports` beyond localhost
- treat the local service as a developer or self-host primitive, not a public hosted control plane

The repository also includes a runnable self-host demo:

```bash
python examples/self_host_sync_quickstart.py
```

That example starts two local registries, pushes one registry's outbox into the
other's inbox, then pulls exported passports into the mirror registry.

If you need the Postgres-backed receiver, install `.[postgres]` and set:

- `FORKIT_SYNC_BACKEND=postgres`
- `FORKIT_SYNC_POSTGRES_DSN=postgresql://...`
- `FORKIT_SYNC_POSTGRES_SCHEMA=public`
- `FORKIT_SYNC_BEARER_TOKEN=...`

## Framework Adapters

`forkit-core` ships thin adapters that preserve the same passport contract
while helping you register framework-specific runtime surfaces.

### LangGraph

- Package: [`forkit_langgraph/`](./forkit_langgraph)
- Example: [`examples/langgraph_sync_quickstart.py`](./examples/langgraph_sync_quickstart.py)
- Install: `pip install -e ".[langgraph]"`

The current adapter supports spec-based registration and runtime-oriented
helpers around builder or compiled graph objects.

### LangChain

- Package: [`forkit_langchain/`](./forkit_langchain)
- Examples: [`examples/langchain_quickstart.py`](./examples/langchain_quickstart.py) and [`examples/langchain_sync_quickstart.py`](./examples/langchain_sync_quickstart.py)
- Install: `pip install -e ".[langchain]"`

The current adapter captures tool metadata and lightweight runtime summaries
without turning the core package into a hard LangChain dependency.

### OpenClaw

- Package: [`forkit_openclaw/`](./forkit_openclaw)
- Example: [`examples/openclaw_quickstart.py`](./examples/openclaw_quickstart.py)

The OpenClaw adapter derives a standard `AgentPassport` from local gateway and
plugin configuration material such as `openclaw.json`, plugin manifests,
extension entrypoints, and hook metadata.

## Hugging Face Model Card Export

Forkit passports add deterministic identity, integrity-ready hashes, and
lineage fields on top of a normal model card workflow. This repo includes a
small compatibility exporter that converts a `ModelPassport` JSON file into a
Hugging Face-style markdown card with YAML front matter.

Included files:

- [`scripts/export_hf_model_card.py`](./scripts/export_hf_model_card.py)
- [`examples/forkit-passport.model.json`](./examples/forkit-passport.model.json)
- [`examples/huggingface-model-card.md`](./examples/huggingface-model-card.md)

Run it locally:

```bash
python scripts/export_hf_model_card.py \
  --path examples/forkit-passport.model.json \
  --output examples/huggingface-model-card.md
```

This exporter is file-based only. It does not call the Hugging Face API.

## Frontend Prototype

A React + TypeScript + Vite frontend lives under [`web/`](./web). It is
included for exploration of the current open-source scope, not as proof of a
hosted control plane.

Current behavior:

- mock-backed in-memory data, not persistent API-backed state
- screens for home, dashboard, registry, search, passport detail, create, verify, lineage, and stats
- useful for demos and product exploration while the durable OSS value stays in the schemas, local registry, SDK, CLI, and examples

Run it locally:

```bash
cd web
npm install
npm run dev
```

Additional commands:

```bash
npm run build
npm run preview
```

Demo screenshots:

| Home | Registry | Inspect |
|---|---|---|
| ![forkit-core home demo](docs/images/home.png) | ![forkit-core registry demo](docs/images/registry.png) | ![forkit-core inspect demo](docs/images/inspect.png) |

## Design Principles

- Offline first. Identity and integrity operations do not require a running service.
- Deterministic identity. The same stable inputs always produce the same `passport_id`.
- Hash-chain provenance. `artifact_hash` and `parent_hash` give you verifiable lineage without central coordination.
- Local JSON as source of truth. SQLite is an index, not the identity authority.
- Keep application metadata outside the identity boundary. Extra UI or sync state should join on `passport_id`, not rewrite it.

For deeper details, read [`docs/identity-spec.md`](./docs/identity-spec.md) and
run [`examples/use_cases.py`](./examples/use_cases.py).

## Community

- GitHub issues and pull requests: use the repository for bugs, proposals, and contribution review
- Website: [forkit.dev](https://forkit.dev)
- Open-source repository: [github.com/Forkit-Dev-Core/Forkit_Dev](https://github.com/Forkit-Dev-Core/Forkit_Dev)
- Discord: [discord.gg/yJ4cdpt7c](https://discord.gg/yJ4cdpt7c)
- Slack: [Forkit Dev workspace](https://join.slack.com/t/forkitdevworkspace/shared_invite/zt-3tgrdgk5v-83aev6ZwE7qQHe_M4q9HIw)

Use GitHub first when the discussion should produce a tracked change.
Use Discord or Slack for earlier discussion, onboarding questions, and community contact.

## Contributing

See [CONTRIBUTING.md](./CONTRIBUTING.md) for contribution workflow,
expectations, and release-sensitive areas.

Before opening a pull request:

- run `ruff check .`
- run `pytest`
- run `python -m build` if you changed packaging or install-facing docs
- run `npm run build` and `npm run lint` in `web/` if you changed the frontend
- update [`docs/identity-spec.md`](./docs/identity-spec.md), examples, and regression tests when you change identity or verification behavior
- do not change `compute_id` without updating the spec and regression anchors

## Roadmap

Near-term open-source priorities:

- strengthen self-hosted registry and sync workflows
- connect more of the web prototype to real local registry and service flows
- deepen framework adapters while keeping the core dependency-light
- improve contributor documentation and adoption examples for serious teams

## License

Apache 2.0. See [LICENSE](./LICENSE).
