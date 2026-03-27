# forkit-core

> Identity and provenance infrastructure for AI models and agents.

[![Python](https://img.shields.io/badge/python-3.10%2B-2f2a62.svg)](#install)
[![Dependencies](https://img.shields.io/badge/dependencies-zero-008190.svg)](#forkit-core)
[![Mode](https://img.shields.io/badge/mode-offline--first-6aa7ab.svg)](#forkit-core)
[![License](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](LICENSE)

`forkit-core` gives every AI model and agent a **cryptographically-identified passport** — a structured, versioned, verifiable record of what it is, where it came from, and what it is authorised to do.

Zero hard dependencies. Works offline. Deterministic IDs.

---

## What's inside

| Module | Purpose |
|---|---|
| `forkit.domain` | Identity derivation, SHA-256 hashing, DAG lineage, integrity verification |
| `forkit.schemas` | `ModelPassport` and `AgentPassport` — dataclass backend (default) or Pydantic v2 (optional) |
| `forkit.registry` | Local filesystem store (JSON files + SQLite index) |
| `forkit.sdk` | `ForkitClient` Python SDK |
| `forkit.cli` | `forkit` command-line tool |

---

## Install

```bash
pip install forkit-core
```

With optional extras:

```bash
pip install "forkit-core[pydantic]"   # Pydantic v2 backend + JSON Schema
pip install "forkit-core[cli]"        # Typer CLI
pip install "forkit-core[all]"        # everything
```

For development:

```bash
git clone https://github.com/arpitasarker01/Forkit_Dev.git
cd Forkit_Dev
pip install -e ".[dev]"
```

### Frontend prototype

A React + TypeScript + Vite frontend lives under [`web/`](./web) and is intentionally limited to the open source Forkit Core scope defined in this README.

For this open source release, the web UI is included for exploration and demonstration. It runs on mock in-memory data; the persistent core already ships in the schemas, local registry, SDK, CLI, and examples, so no backend API is required to explore the current release.

Frontend setup:

```bash
cd web
npm install
npm run dev
```

Additional frontend commands:

```bash
npm run build
npm run preview
```

The frontend includes these screens:

- Home
- Dashboard
- Registry
- Search
- Passport Detail / Inspect
- Register Passport
- Verify Passport
- Lineage
- Registry Stats

Registry is the browse view, Search is for filtering existing passports, and Register Passport creates a new mock-backed record for demonstration.

### Demo screenshots

The included web demo is mock-backed and intended for exploration of the open source Forkit Core concepts that already ship in the schemas, local registry, SDK, CLI, and examples.

| Home | Registry | Inspect |
|---|---|---|
| ![Forkit Core Home demo](docs/images/home.png) | ![Forkit Core Registry demo](docs/images/registry.png) | ![Forkit Core Inspect demo](docs/images/inspect.png) |

### GitHub passport validation

Forkit Core now includes a lightweight GitHub-native integration for validating a committed passport file in CI. It checks that the file exists, validates the JSON against the current open source `ModelPassport` or `AgentPassport` schema, and verifies that the stored deterministic `id` matches the file content.

Included files:

- [`.github/actions/validate-passport/action.yml`](./.github/actions/validate-passport/action.yml) for reusable CI validation
- [`.github/workflows/validate-passport.yml`](./.github/workflows/validate-passport.yml) as a sample workflow
- [`scripts/validate_passport.py`](./scripts/validate_passport.py) for local and CI validation
- [`scripts/generate_passport_template.py`](./scripts/generate_passport_template.py) for a starter `forkit-passport.json`

Generate a starter passport:

```bash
python scripts/generate_passport_template.py --passport-type model --output forkit-passport.json
```

Validate a passport locally:

```bash
python scripts/validate_passport.py --path forkit-passport.json
```

Use the action from another repository:

```yaml
- uses: arpitasarker01/Forkit_Dev/.github/actions/validate-passport@main
  with:
    passport-path: forkit-passport.json
```

This repo's sample workflow validates [`examples/forkit-passport.model.json`](./examples/forkit-passport.model.json). In your own repo, point `passport-path` to the file you want to enforce in CI.

---

## Quickstart — SDK

```python
from forkit.sdk import ForkitClient

client = ForkitClient()  # defaults to ~/.forkit/registry

# Register a model
model_id = client.models.register(
    name="my-fine-tuned-llm",
    version="1.0.0",
    architecture="transformer",
    creator={"name": "Hamza", "organization": "ForkIt"},
    license="Apache-2.0",
)

# Register an agent on top of that model
agent_id = client.agents.register(
    name="support-agent",
    version="1.0.0",
    model_id=model_id,
    creator={"name": "Hamza", "organization": "ForkIt"},
    system_prompt="You are a helpful support assistant.",
)

# Trace lineage
for node in client.lineage.ancestors(agent_id):
    print(node)

# Verify integrity
print(client.verify(model_id))
```

---

## Quickstart — CLI

```bash
# Register from YAML
forkit register model examples/register_model.yaml
forkit register agent examples/register_agent.yaml

# Inspect
forkit inspect <passport-id>

# List and search
forkit list --type model --status active
forkit search "llama"

# Trace lineage
forkit lineage <passport-id>

# Verify integrity
forkit verify <passport-id>

# Registry stats
forkit stats
```

---

## Passport structure

### ModelPassport

| Field | Description |
|---|---|
| `id` | Deterministic SHA-256 of `(type, name, version, creator, artifact_hash)` |
| `architecture` | e.g. `transformer`, `diffusion`, `mamba` |
| `artifact_hash` | SHA-256 of model weight files |
| `parent_hash` | SHA-256 of parent artifact (fine-tune chain) |
| `base_model_id` | Passport ID of the parent model (lineage link) |
| `training_data` | Dataset references with optional hashes |
| `capabilities` | Modalities, context length, benchmarks |

### AgentPassport

| Field | Description |
|---|---|
| `id` | Deterministic SHA-256 of `(type, name, version, creator, artifact_hash)` |
| `model_id` | Required — full passport ID of the underlying `ModelPassport` |
| `system_prompt` | Stored as a hash record (content + hash, not raw text) |
| `tools` | List of `ToolRef` with name, version, optional hash |
| `parent_agent_id` | Passport ID of the parent agent (fork lineage) |
| `endpoint_hash` | SHA-256 of deployment endpoint configuration |

---

## Registry layout

```
~/.forkit/registry/
  index.db          ← SQLite index (always rebuildable)
  lineage.json      ← Lineage graph snapshot
  models/
    <sha256>.json   ← One file per ModelPassport
  agents/
    <sha256>.json   ← One file per AgentPassport
```

---

## Schema use cases

All 10 use cases are validated by `tests/test_use_cases.py` and demonstrated interactively:

```bash
python3 examples/use_cases.py
```

---

### Use case 1 — Register a base model passport

`id` is derived deterministically from name, version, creator, and (optionally) artifact hash. No server needed.

```python
from forkit.schemas import ModelPassport, TaskType, Architecture, PassportStatus

passport = ModelPassport(
    name            = "llama-3-8b-base",
    version         = "1.0.0",
    task_type       = TaskType.TEXT_GENERATION,
    architecture    = Architecture.DECODER_ONLY,
    creator         = {"name": "Meta", "organization": "Meta AI"},
    parameter_count = 8_000_000_000,
    status          = PassportStatus.ACTIVE,
)
print(passport.id)          # deterministic 64-char SHA-256
print(passport.short_id())  # first 12 chars
```

**Invariant:** same inputs → same `id`, always.

---

### Use case 2 — Fine-tuned model with artifact_hash and parent_hash

Attach the hash of the model weights as `artifact_hash`. Point `parent_hash` at the base model weights to create a verifiable hash chain without a registry.

```python
from forkit.domain import HashEngine

H = HashEngine()
weights_hash = H.hash_file("/models/ft/model.safetensors")

ft = ModelPassport(
    name               = "llama-3-8b-ft",
    version            = "1.0.0",
    task_type          = TaskType.INSTRUCTION_FOLLOWING,
    architecture       = Architecture.DECODER_ONLY,
    creator            = {"name": "Alice"},
    artifact_hash      = weights_hash,
    parent_hash        = H.hash_string("base-llama-3-8b-weights-v1"),
    fine_tuning_method = "LoRA",
)
```

**Invariant:** `artifact_hash` is mixed into `id`, so two passports with identical metadata but different weights always have different IDs.

---

### Use case 3 — Agent passport linked to a model

`model_id` holds the full 64-char passport ID of the underlying `ModelPassport`. This is a hard cryptographic link — no lookup required to verify it.

```python
from forkit.schemas import AgentPassport, AgentTaskType, AgentArchitecture

agent = AgentPassport(
    name         = "support-agent",
    version      = "1.0.0",
    model_id     = ft.id,          # full 64-char passport ID
    task_type    = AgentTaskType.CUSTOMER_SUPPORT,
    architecture = AgentArchitecture.REACT,
    creator      = {"name": "Alice"},
    tools        = [{"name": "kb_search", "version": "1.2.0"}],
)
assert agent.model_id == ft.id
```

---

### Use case 4 — artifact_hash drives the passport ID

```python
base = dict(name="model", version="1.0.0", task_type=..., architecture=..., creator=...)

m_a = ModelPassport(**base, artifact_hash="a" * 64)
m_b = ModelPassport(**base, artifact_hash="b" * 64)

assert m_a.id != m_b.id                                          # different artifacts → different IDs
assert m_a.id == ModelPassport(**base, artifact_hash="a" * 64).id  # deterministic
```

---

### Use case 5 — Hash a real artifact → tamper detection

```python
artifact_hash = H.hash_artifact("/models/llama-3-8b-ft/")
passport = ModelPassport(**base, artifact_hash=artifact_hash)

# Verify later — True if weights unchanged
assert H.verify_artifact("/models/llama-3-8b-ft/", passport.artifact_hash)

# After any file change, verification fails
assert not H.verify_artifact("/path/to/modified/", passport.artifact_hash)
```

---

### Use case 6 — Fork an agent (parent_agent_id + parent_hash chain)

```python
parent_hash = H.hash_config({"prompt": "...", "tools": [...], "temperature": 0.3})
parent = AgentPassport(..., artifact_hash=parent_hash)

forked = AgentPassport(
    ...,
    artifact_hash     = H.hash_config({...}),    # new config
    parent_hash       = parent_hash,              # == parent.artifact_hash
    parent_agent_id   = parent.id,               # passport ID for lineage graph
    parent_agent_name = parent.name,
    fork_reason       = "Added Arabic support",
)
assert forked.parent_hash == parent.artifact_hash
assert forked.parent_agent_id == parent.id
```

---

### Use case 7 — Trace lineage: ancestors and descendants

```python
from forkit.domain import LineageGraph, LineageNode, LineageEdge, NodeType, EdgeType

g = LineageGraph()
g.add_node(LineageNode(base.id,  NodeType.MODEL, base.name,  base.version))
g.add_node(LineageNode(ft.id,    NodeType.MODEL, ft.name,    ft.version))
g.add_node(LineageNode(agent.id, NodeType.AGENT, agent.name, agent.version))
g.add_edge(LineageEdge(ft.id,    base.id, EdgeType.DERIVED_FROM, "LoRA"))
g.add_edge(LineageEdge(agent.id, ft.id,   EdgeType.BUILT_ON))

g.ancestors(agent.id)    # [ft, base]
g.descendants(base.id)   # [ft, agent]
g.save("/registry/lineage.json")
```

**Invariant:** `add_edge` raises `ValueError` on cycle detection.

---

### Use case 8 — Verify passport integrity

```python
from forkit.domain import verify_passport_id

result = verify_passport_id(passport.to_dict())
# {"valid": True, "reason": "ok", "stored_id": "...", "derived_id": "..."}

# Strip id → force re-derivation
d = {k: v for k, v in passport.to_dict().items() if k != "id"}
restored = ModelPassport.from_dict(d)
assert restored.id == passport.id
```

---

### Use case 9 — Serialise → dict → deserialise roundtrip

```python
import json

d = passport.to_dict()               # enums → strings, nested objects → dicts
s = json.dumps(d, indent=2)

restored = ModelPassport.from_dict(json.loads(s))
assert restored.id            == passport.id
assert restored.artifact_hash == passport.artifact_hash
```

---

### Use case 10 — Reject invalid hash values

```python
from forkit.domain.identity import validate_hash

validate_hash("A" * 64)   # → "a"*64  (normalised to lowercase, accepted)
validate_hash("abc123")   # → ValueError (too short)
validate_hash("z" * 64)   # → ValueError (non-hex)

# is_valid_hash is STRICT — no normalisation
from forkit.domain import HashEngine
HashEngine.is_valid_hash("a" * 64)   # True
HashEngine.is_valid_hash("A" * 64)   # False (uppercase rejected)

# Raises on construction
ModelPassport(..., artifact_hash="NOT-VALID")  # ValueError
```

---

## Design principles

**Offline-first.** All identity and integrity operations work without a network connection or a running server.

**Hash-chain provenance.** `artifact_hash` (content fingerprint) and `parent_hash` (lineage link) form a verifiable chain without PKI or a central authority.

**Two backends, one interface.** The dataclass backend has zero external dependencies and runs on any Python 3.10+ installation. Install `pydantic>=2` for JSON Schema generation and `.model_validate()` / `.model_dump()` support.

**SQLite as a rebuildable index.** JSON files are the source of truth. SQLite is always rebuildable from JSON via `LocalRegistry.rebuild_index()`.

For a full specification of the identity contract, hash rules, and serialisation guarantees, see [`docs/identity-spec.md`](docs/identity-spec.md).

---

## Contributing

Contributions are welcome. Please open an issue before submitting a large pull request.

- Run `pytest -v tests/` before submitting
- Run `ruff check forkit/` and fix any lint errors
- Do not change `compute_id` without updating `docs/identity-spec.md` and the regression anchors

---

## License

Apache 2.0 — see [LICENSE](LICENSE)
