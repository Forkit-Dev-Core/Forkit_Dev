# forkit-core — Identity Specification

**Version:** 1
**Status:** Stable
**Last updated:** 2026-03-16

This document is the canonical reference for how passport IDs are computed, how
hash-chain provenance works, and what the serialisation contract guarantees.
Nothing described here may change without a major version bump and a migration
guide.

---

## 1. Passport types

Two first-class passport types exist:

| Type    | Class            | `passport_type` value |
|---------|------------------|-----------------------|
| Model   | `ModelPassport`  | `"model"`             |
| Agent   | `AgentPassport`  | `"agent"`             |

The `passport_type` field is set automatically by each class and is immutable
after construction. It participates in ID derivation (see §3).

---

## 2. Identity fields

The **identity fields** are the minimal set of inputs that uniquely name a
passport. They are the only fields that feed into the ID hash:

| Field           | Source                        | Notes                               |
|-----------------|-------------------------------|-------------------------------------|
| `passport_type` | class-level constant          | `"model"` or `"agent"`              |
| `name`          | required constructor argument | human-readable name                 |
| `version`       | required constructor argument | 2- or 3-part semver (`1.0` / `1.0.0`) |
| `creator.name`  | required constructor argument | individual or org name              |
| `creator.org`   | optional constructor argument | `None` when omitted                 |
| `artifact_hash` | optional constructor argument | SHA-256 of the model weights / agent config |

All other fields (description, tags, metadata, timestamps, etc.) are
**non-identity** — changing them does not change the passport ID.

### 2.1 Additional metadata fields

Application and integration metadata must remain outside the identity material.
Examples include:

- sync state
- labels or UI annotations
- review notes
- runtime configuration
- integration-specific routing fields

These fields may be stored alongside the passport and joined by `passport_id`,
either in a sidecar table/document or under a namespaced metadata block such as
`metadata.context`. They must not be copied into the ID inputs.

Important: `creator.organization` is provenance and does participate in the ID.
It is not the same thing as later routing, sync, or application ownership data.

---

## 3. ID derivation algorithm

```
canonical_json = json.dumps(
    {
        "passport_type": <passport_type>,
        "name":          <name>,
        "version":       <version>,
        "creator_name":  <creator.name>,
        "creator_org":   <creator.organization>,   # None when absent
    },
    sort_keys = True,
    # encoding: UTF-8 (Python default)
)

if artifact_hash is not None:
    payload = artifact_hash + "|" + canonical_json
else:
    payload = canonical_json

id = sha256(payload.encode("utf-8")).hexdigest()
```

This algorithm is implemented in `forkit.domain.identity.compute_id` and is the
**single source of truth** for both the dataclass backend and the optional
Pydantic v2 backend.

**Invariants:**

1. Same inputs always produce the same `id` — deterministic, offline, no
   server required.
2. Two passports with identical metadata but different `artifact_hash` values
   always get different IDs, because `artifact_hash` is mixed into the payload.
3. `artifact_hash` is normalised to lowercase before entering the computation
   (see §4). Uppercase input is accepted and silently normalised.
4. `creator_org = None` and `creator_org = ""` are NOT equivalent. Pass `None`
   (or omit the key) when no organisation applies; do not pass an empty string.

---

## 4. Hash field rules

All hash fields (`artifact_hash`, `parent_hash`, `endpoint_hash`,
`base_model_id`, `parent_agent_id`) must be valid SHA-256 hex digests when
provided.

### 4.1 `validate_hash` — user-input normalisation

Used on every hash field at construction time:

- Accepts `None` → returns `None`.
- Accepts a 64-character string of `[0-9a-fA-F]` → normalises to lowercase,
  returns the lowercased value.
- Any other value → raises `ValueError`.

### 4.2 `is_valid_hash` — strict verification

Used inside `HashEngine` and in assertions:

- Returns `True` only for exactly 64 lowercase hex characters.
- `"A" * 64` returns `False` — uppercase is **not** accepted.
- Use `validate_hash` first if you need to accept user-supplied strings.

---

## 5. Hash-chain provenance

Two fields on every passport form a verifiable hash chain without PKI or a
central registry:

| Field           | What it hashes                                  |
|-----------------|-------------------------------------------------|
| `artifact_hash` | Content fingerprint — the model weights, agent config bundle, etc. |
| `parent_hash`   | SHA-256 of the **parent artifact** — the base model weights for a fine-tune, the parent config for an agent fork. |

A verifier can confirm the chain holds by checking:

```python
from forkit.domain import HashEngine, verify_passport_id

H = HashEngine()

# 1. Passport ID is internally consistent
result = verify_passport_id(passport.to_dict())
assert result["valid"]

# 2. Artifact content matches the recorded hash
assert H.verify_artifact("/path/to/artifact/", passport.artifact_hash)

# 3. Parent relationship is unbroken
assert passport.parent_hash == H.hash_artifact("/path/to/parent/artifact/")
```

None of these checks require network access.

---

## 6. Lineage passport IDs

Two fields carry the passport IDs of related passports for programmatic lineage
wiring (used by `LineageGraph.register_model` and `register_agent`):

| Field            | Present on       | Meaning                              |
|------------------|------------------|--------------------------------------|
| `base_model_id`  | `ModelPassport`  | Passport ID of the parent model (fine-tune lineage) |
| `parent_agent_id`| `AgentPassport`  | Passport ID of the parent agent (fork lineage) |

These are distinct from `parent_hash`:

- `parent_hash` is a **content** fingerprint (hash of artifact bytes).
- `base_model_id` / `parent_agent_id` are **passport IDs** (hash of identity fields).

Both are validated as 64-char hex at construction time.

---

## 7. Version validation

`version` must be a 2- or 3-part semver string:

```
valid:   "1.0",  "1.0.0",  "2.4.1",  "0.1"
invalid: "1",  "1.0.0.0",  "v1.0.0",  "latest"
```

The `v` prefix is not accepted. Strip it before constructing a passport.

---

## 8. Serialisation contract

`to_dict()` returns a JSON-safe plain dict:

- Enum fields are serialised as their `.value` string.
- `datetime` fields are serialised as ISO 8601 strings.
- Nested dataclass / Pydantic objects are recursively expanded to dicts.
- The dict is reproducibly round-trippable via `from_dict()`.

```python
import json
d = passport.to_dict()
s = json.dumps(d)
restored = ModelPassport.from_dict(json.loads(s))
assert restored.id == passport.id
```

`passport_type` is present in `to_dict()` output but is stripped by
`from_dict()` before construction (it is set by the class, not the caller).

---

## 9. Deterministic regression anchors

The following IDs were produced by `examples/use_cases.py` with the inputs
documented in that file. They serve as regression anchors — any change that
alters these values is a **breaking change** to the identity contract.

| Passport                    | ID (first 16 chars)   |
|-----------------------------|-----------------------|
| `llama-3-8b-base` v1.0.0    | `1bdfbcb0d6a96a6b...` |
| `llama-3-8b-ft` v1.0.0      | `e919ef1354ef2cb1...` |
| `support-agent` v1.0.0      | `3e13ce3909ea49de...` |

Full IDs are printed by running `python3 examples/use_cases.py`.

---

## 10. Implementation locations

| Concern                  | File                                    |
|--------------------------|-----------------------------------------|
| ID derivation            | `forkit/domain/identity.py`             |
| Hash engine              | `forkit/domain/hashing.py`              |
| Lineage DAG              | `forkit/domain/lineage.py`              |
| Integrity verification   | `forkit/domain/integrity.py`            |
| Dataclass schemas        | `forkit/schemas/model.py`, `agent.py`   |
| Pydantic v2 schemas      | `forkit/schemas/pydantic/model.py`, `agent.py` |
| Shared Pydantic types    | `forkit/schemas/pydantic/_types.py`     |
| Public schema interface  | `forkit/schemas/__init__.py`            |

---

## 11. Stability guarantees

| Element                        | Stability                  |
|--------------------------------|----------------------------|
| `compute_id` inputs → output   | **Frozen** in v1           |
| `validate_hash` / `is_valid_hash` semantics | **Frozen** in v1 |
| `to_dict` / `from_dict` roundtrip | **Frozen** in v1        |
| Field names on `ModelPassport` / `AgentPassport` | Additive-only in v0.x |
| Enum values                    | Additive-only in v0.x      |
| `LineageGraph` serialisation format | Stable in v0.1.0     |

Any change that breaks the ID derivation or serialisation roundtrip will
increment the **major** version and will be accompanied by a migration script.
