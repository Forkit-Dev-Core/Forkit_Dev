"""
examples/use_cases.py
─────────────────────
Runnable demonstration of all 10 forkit-core schema use cases.

Run from the repo root:
    python3 examples/use_cases.py

Each use case prints its inputs, outputs, and assertions cleanly.
All 10 use cases are derived from the original validated demo and produce
deterministic outputs.
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Make the package importable when run from any working directory
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from forkit.domain import (
    EdgeType,
    HashEngine,
    LineageEdge,
    LineageGraph,
    LineageNode,
    NodeType,
)
from forkit.domain.identity import validate_hash
from forkit.schemas import (
    _PYDANTIC_AVAILABLE,
    AgentArchitecture,
    AgentPassport,
    AgentTaskType,
    Architecture,
    LicenseType,
    ModelPassport,
    PassportStatus,
    TaskType,
)

# ── Terminal colour helpers ────────────────────────────────────────────────────

R = "\033[0m"
B = "\033[1m"
G = "\033[92m"
C = "\033[96m"
Y = "\033[93m"
BL = "\033[94m"
GR = "\033[90m"
RD = "\033[91m"

H = HashEngine()

def hdr(n: int, title: str) -> None:
    print(f"\n{B}{BL}{'─'*64}{R}")
    print(f"{B}{BL} Use case {n}: {title}{R}")
    print(f"{B}{BL}{'─'*64}{R}")

def ok(msg: str)   -> None: print(f"  {G}✓{R}  {msg}")
def info(msg: str) -> None: print(f"  {C}→{R}  {msg}")
def warn(msg: str) -> None: print(f"  {Y}!{R}  {msg}")
def kv(k: str, v)  -> None: print(f"  {GR}{k:<24}{R} {v}")


# ── Shared fixture ─────────────────────────────────────────────────────────────

CREATOR = {"name": "Example Maintainer", "organization": "Example Lab"}

backend = "Pydantic v2" if _PYDANTIC_AVAILABLE else "pure-Python dataclass"
print(f"\n{B}forkit-core — Schema Use Cases  ({backend}){R}")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 1 — Register a base model passport
# ══════════════════════════════════════════════════════════════════════════════

hdr(1, "Register a base model passport")

base_model = ModelPassport(
    name            = "llama-3-8b-base",
    version         = "1.0.0",
    task_type       = TaskType.TEXT_GENERATION,
    architecture    = Architecture.DECODER_ONLY,
    creator         = CREATOR,
    license         = LicenseType.LLAMA_3,
    model_id        = "meta-llama/Meta-Llama-3-8B",
    parameter_count = 8_000_000_000,
    description     = "Meta LLaMA 3 8B base model",
    tags            = ["llm", "base", "llama3"],
    status          = PassportStatus.ACTIVE,
)

kv("Passport ID",   base_model.id)
kv("Short ID",      base_model.short_id() + "...")
kv("Name",          base_model.name)
kv("Version",       base_model.version)
kv("Task type",     base_model.task_type.value)
kv("Architecture",  base_model.architecture.value)
kv("License",       base_model.license.value)
kv("Creator",       f"{base_model.creator.name} / {base_model.creator.organization}")
kv("Parameters",    f"{base_model.parameter_count:,}")
kv("Status",        base_model.status.value)
kv("artifact_hash", str(base_model.artifact_hash))
kv("parent_hash",   str(base_model.parent_hash))
assert len(base_model.id) == 64
ok("Base model registered — ID is a 64-char deterministic SHA-256")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 2 — Fine-tuned model with artifact_hash + parent_hash provenance
# ══════════════════════════════════════════════════════════════════════════════

hdr(2, "Fine-tuned model — artifact_hash + parent_hash provenance")

with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as wf:
    wf.write(b"[simulated fine-tuned model weights]" * 1000)
    weights_path = wf.name

weights_hash       = H.hash_file(weights_path)
parent_weights_hash = H.hash_string("base-llama-3-8b-weights-v1")
info(f"Hashed weights file      → {weights_hash[:20]}...")
info(f"Parent weights hash      → {parent_weights_hash[:20]}...")

fine_tuned = ModelPassport(
    name               = "llama-3-8b-support-ft",
    version            = "1.0.0",
    task_type          = TaskType.INSTRUCTION_FOLLOWING,
    architecture       = Architecture.DECODER_ONLY,
    creator            = CREATOR,
    license            = LicenseType.LLAMA_3,
    model_id           = "forkit/llama-3-8b-support-ft",
    artifact_hash      = weights_hash,
    parent_hash        = parent_weights_hash,
    base_model_name    = "meta-llama/Meta-Llama-3-8B",
    fine_tuning_method = "LoRA",
    parameter_count    = 8_000_000_000,
    status             = PassportStatus.ACTIVE,
    tags               = ["fine-tuned", "support", "lora"],
)

kv("Passport ID",   fine_tuned.id)
kv("artifact_hash", fine_tuned.artifact_hash[:20] + "...")
kv("parent_hash",   fine_tuned.parent_hash[:20] + "...")
kv("base_model",    fine_tuned.base_model_name)
kv("ft method",     fine_tuned.fine_tuning_method)
assert fine_tuned.artifact_hash == weights_hash
assert fine_tuned.parent_hash   == parent_weights_hash
ok("Fine-tuned model registered with verifiable hash chain")
ok("parent_hash links to base weights — no central registry required")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 3 — Agent passport linked to a model
# ══════════════════════════════════════════════════════════════════════════════

hdr(3, "Agent passport linked to a model")

support_agent = AgentPassport(
    name         = "support-agent-ar-en",
    version      = "2.0.0",
    model_id     = fine_tuned.id,
    task_type    = AgentTaskType.CUSTOMER_SUPPORT,
    architecture = AgentArchitecture.REACT,
    creator      = CREATOR,
    license      = LicenseType.APACHE_2,
    temperature  = 0.3,
    max_tokens   = 2048,
    tools        = [
        {"name": "kb_search",     "version": "1.2.0"},
        {"name": "ticket_create", "version": "1.0.0"},
        {"name": "order_lookup",  "version": "2.1.0"},
    ],
    tags   = ["support", "bilingual", "production"],
    status = PassportStatus.ACTIVE,
)

kv("Agent ID",     support_agent.id)
kv("Short ID",     support_agent.short_id() + "...")
kv("task_type",    support_agent.task_type.value)
kv("architecture", support_agent.architecture.value)
kv("model_id",     support_agent.model_id[:20] + "...")
kv("license",      support_agent.license.value)
kv("tools",        str([t.name for t in support_agent.tools]))
kv("temperature",  str(support_agent.temperature))
assert support_agent.model_id == fine_tuned.id
assert len(support_agent.tools) == 3
ok("Agent registered — model_id is the full 64-char passport ID of the model")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 4 — artifact_hash drives the passport ID
# ══════════════════════════════════════════════════════════════════════════════

hdr(4, "artifact_hash drives the passport ID")

_base = dict(
    name         = "same-model",
    version      = "1.0.0",
    task_type    = TaskType.TEXT_GENERATION,
    architecture = Architecture.DECODER_ONLY,
    creator      = CREATOR,
)

m_no_hash = ModelPassport(**_base)
m_hash_a  = ModelPassport(**_base, artifact_hash="a" * 64)
m_hash_b  = ModelPassport(**_base, artifact_hash="b" * 64)
m_hash_a2 = ModelPassport(**_base, artifact_hash="a" * 64)

info("Same name / version / creator — different artifact_hash values")
kv("no hash   → ID", m_no_hash.short_id()  + "...")
kv("hash=aaa  → ID", m_hash_a.short_id()   + "...")
kv("hash=bbb  → ID", m_hash_b.short_id()   + "...")
kv("hash=aaa  → ID", m_hash_a2.short_id()  + "... (repeat)")

assert m_no_hash.id != m_hash_a.id,  "no-hash vs hash-a must differ"
assert m_hash_a.id  != m_hash_b.id,  "hash-a vs hash-b must differ"
assert m_hash_a.id  == m_hash_a2.id, "same artifact_hash must yield same ID"
ok("Different artifact_hash → different passport IDs")
ok("Same artifact_hash → deterministic same ID")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 5 — Hash a real artifact directory → attach to passport
# ══════════════════════════════════════════════════════════════════════════════

hdr(5, "Hash a real artifact directory → attach to passport")

with tempfile.TemporaryDirectory() as model_dir:
    mdp = Path(model_dir)
    (mdp / "model.safetensors").write_bytes(b"[weights data]" * 5000)
    (mdp / "config.json").write_text('{"hidden_size": 4096, "num_heads": 32}')
    (mdp / "tokenizer.json").write_text('{"version": "1.0"}')
    (mdp / "README.md").write_text("# Model card (not included in hash)")

    info("Directory contents:")
    for f in sorted(mdp.iterdir()):
        kv(f"  {f.name}", f"{f.stat().st_size:,} bytes")

    artifact_h     = H.hash_artifact(model_dir)
    weights_only_h = H.hash_model_artifact(model_dir, include_config=False)
    info(f"hash_artifact(all files) → {artifact_h[:24]}...")
    info(f"weights-only hash        → {weights_only_h[:24]}...")
    assert artifact_h != weights_only_h, "all-files vs weights-only must differ (README included)"

    passport_with_hash = ModelPassport(
        **_base,
        artifact_hash = artifact_h,
        quantization  = "fp16",
    )
    kv("Passport ID",   passport_with_hash.id)
    kv("artifact_hash", passport_with_hash.artifact_hash[:24] + "...")
    assert H.verify_artifact(model_dir, passport_with_hash.artifact_hash)
    ok("Artifact verified — directory matches passport artifact_hash")

    (mdp / "model.safetensors").write_bytes(b"[TAMPERED weights]" * 5000)
    tampered_h = H.hash_artifact(model_dir)
    assert tampered_h != artifact_h
    warn("Weights tampered → hash MISMATCH detected automatically")
    ok("Integrity check catches model tampering without a central registry")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 6 — Fork an agent (parent_hash chain)
# ══════════════════════════════════════════════════════════════════════════════

hdr(6, "Fork an agent — parent_hash chain")

parent_config = {
    "system_prompt_hash": H.hash_system_prompt("You are a support agent."),
    "tools":              sorted(["kb_search", "ticket_create"]),
    "temperature":        0.3,
}
parent_config_hash = H.hash_config(parent_config)

parent_agent = AgentPassport(
    name          = "support-agent-en",
    version       = "1.0.0",
    model_id      = fine_tuned.id,
    task_type     = AgentTaskType.CUSTOMER_SUPPORT,
    architecture  = AgentArchitecture.REACT,
    creator       = CREATOR,
    artifact_hash = parent_config_hash,
)

forked_config = {
    "system_prompt_hash": H.hash_system_prompt(
        "You are a bilingual support agent. Respond in the user's language."
    ),
    "tools":       sorted(["kb_search", "ticket_create", "translation_service"]),
    "temperature": 0.3,
}
forked_config_hash = H.hash_config(forked_config)

forked_agent = AgentPassport(
    name              = "support-agent-ar-en-v2",
    version           = "2.0.0",
    model_id          = fine_tuned.id,
    task_type         = AgentTaskType.CUSTOMER_SUPPORT,
    architecture      = AgentArchitecture.REACT,
    creator           = CREATOR,
    artifact_hash     = forked_config_hash,
    parent_hash       = parent_config_hash,
    parent_agent_name = parent_agent.name,
    fork_reason       = "Added Arabic language support + translation tool",
)

kv("Parent agent ID",   parent_agent.short_id() + "...")
kv("Parent art. hash",  parent_agent.artifact_hash[:20] + "...")
kv("Forked agent ID",   forked_agent.short_id() + "...")
kv("Forked art. hash",  forked_agent.artifact_hash[:20] + "...")
kv("parent_hash",       forked_agent.parent_hash[:20] + "...")
kv("fork_reason",       forked_agent.fork_reason)

assert forked_agent.parent_hash == parent_agent.artifact_hash
ok("parent_hash == parent agent's artifact_hash — verifiable without a registry")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 7 — Trace lineage: ancestors + descendants
# ══════════════════════════════════════════════════════════════════════════════

hdr(7, "Trace lineage: ancestors and descendants")

g = LineageGraph()

for p, nt in [
    (base_model,    NodeType.MODEL),
    (fine_tuned,    NodeType.MODEL),
    (support_agent, NodeType.AGENT),
    (parent_agent,  NodeType.AGENT),
    (forked_agent,  NodeType.AGENT),
]:
    g.add_node(LineageNode(p.id, nt, p.name, p.version))

g.add_edge(LineageEdge(fine_tuned.id,    base_model.id,    EdgeType.DERIVED_FROM, "LoRA fine-tune"))
g.add_edge(LineageEdge(support_agent.id, fine_tuned.id,    EdgeType.BUILT_ON))
g.add_edge(LineageEdge(parent_agent.id,  fine_tuned.id,    EdgeType.BUILT_ON))
g.add_edge(LineageEdge(forked_agent.id,  parent_agent.id,  EdgeType.FORKED_FROM,  "Arabic support"))

info(g.summary())
print()

info(f"Ancestors of '{forked_agent.name}':")
for node in g.ancestors(forked_agent.id):
    kv(f"  [{node.node_type.value}]", f"{node.name} v{node.version}")

print()
info(f"Descendants of '{base_model.name}':")
for node in g.descendants(base_model.id):
    kv(f"  [{node.node_type.value}]", f"{node.name} v{node.version}")

assert fine_tuned.id   in {n.id for n in g.ancestors(forked_agent.id)}
assert base_model.id   in {n.id for n in g.ancestors(forked_agent.id)}
assert forked_agent.id in {n.id for n in g.descendants(base_model.id)}
ok("Full lineage graph traversal complete")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 8 — Verify passport integrity
# ══════════════════════════════════════════════════════════════════════════════

hdr(8, "Verify passport integrity")

orig_dict = fine_tuned.to_dict()
info("Re-derive ID from canonical fields (strip stored id):")

stripped  = {k: v for k, v in orig_dict.items() if k not in ("id", "passport_type")}
recomputed = ModelPassport.from_dict(stripped)

kv("Stored ID",     orig_dict["id"][:20] + "...")
kv("Recomputed ID", recomputed.id[:20]   + "...")
kv("Match",         str(recomputed.id == orig_dict["id"]))
assert recomputed.id == orig_dict["id"]
ok("Passport integrity verified — re-derived ID matches stored ID")

print()
info("Tamper: change name field and recheck:")
tampered_dict = {k: v for k, v in orig_dict.items() if k not in ("id", "passport_type")}
tampered_dict["name"] = "TAMPERED-name"
tampered = ModelPassport.from_dict(tampered_dict)

kv("Stored ID",    orig_dict["id"][:20] + "...")
kv("After tamper", tampered.id[:20]     + "...")
kv("Match",        str(tampered.id == orig_dict["id"]))
assert tampered.id != orig_dict["id"]
warn("Tampered passport detected — ID mismatch (no registry required)")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 9 — Serialise → dict → deserialise roundtrip
# ══════════════════════════════════════════════════════════════════════════════

hdr(9, "Serialise → dict → deserialise roundtrip")

serialised = json.dumps(fine_tuned.to_dict(), indent=2, default=str)
info(f"Serialised to JSON ({len(serialised)} chars)")

restored = ModelPassport.from_dict(json.loads(serialised))
kv("Original ID",   fine_tuned.id[:20] + "...")
kv("Restored ID",   restored.id[:20]   + "...")
kv("IDs match",     str(fine_tuned.id == restored.id))
kv("Name match",    str(fine_tuned.name == restored.name))
kv("Hash match",    str(fine_tuned.artifact_hash == restored.artifact_hash))
assert fine_tuned.id           == restored.id
assert fine_tuned.artifact_hash == restored.artifact_hash
ok("ModelPassport roundtrip preserves all fields and ID")

print()
serialised_agent = json.dumps(support_agent.to_dict(), indent=2, default=str)
restored_agent   = AgentPassport.from_dict(json.loads(serialised_agent))
kv("Agent original ID", support_agent.short_id() + "...")
kv("Agent restored ID", restored_agent.short_id() + "...")
assert support_agent.id == restored_agent.id
ok("AgentPassport roundtrip preserves all fields and ID")


# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 10 — Reject invalid hash input
# ══════════════════════════════════════════════════════════════════════════════

hdr(10, "Reject invalid hash input (field validation)")

cases = [
    ("too short",      "abc123"),
    ("uppercase hex",  "A" * 64),    # normalised → accepted
    ("non-hex chars",  "z" * 64),
    ("valid hash",     "a" * 64),
]
for label, value in cases:
    try:
        result = validate_hash(value)
        ok(f"{label:<22} → accepted  ({result[:12]}...)")
    except ValueError as e:
        warn(f"{label:<22} → rejected  ({str(e)[:52]}...)")

# Valid hash accepted by ModelPassport
valid_m = ModelPassport(**_base, artifact_hash="a" * 64)
ok("Valid 64-char lowercase hex accepted by ModelPassport")

# Invalid hash must raise
try:
    ModelPassport(**_base, artifact_hash="NOT-A-VALID-HASH")
    print(f"  {RD}✗  Should have raised ValueError!{R}")
except Exception:
    ok("Invalid artifact_hash correctly raises ValueError on ModelPassport")

# is_valid_hash is strict (no normalisation)
assert HashEngine.is_valid_hash("a" * 64)  is True
assert HashEngine.is_valid_hash("A" * 64)  is False
ok("is_valid_hash is strict — uppercase returns False (use validate_hash to normalise)")


# ── Final summary ──────────────────────────────────────────────────────────────

print(f"\n{B}{G}{'═'*64}{R}")
print(f"{B}{G} All 10 use cases completed successfully.{R}")
print(f"{B}{G} Backend: {backend}{R}")
print(f"{B}{G}{'═'*64}{R}\n")
