"""
forkit-core schema use cases — runnable demo.

Imports everything from the forkit_core package.  When Pydantic v2 is
installed, the real Pydantic models are used.  When it is not available,
the package automatically falls back to the pure-Python _compat layer —
all 10 use cases run identically in both cases.

Run from the repo root:
    python3 scripts/demo_passports.py
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

# Make the repo root importable when run directly
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# ── forkit_core imports ────────────────────────────────────────────────────────
from forkit_core import (
    _PYDANTIC_AVAILABLE,
    AgentPassport,
    ModelPassport,
)
from forkit_core.hashing.engine import HashEngine as H
from forkit_core.lineage.graph import (
    EdgeType,
    LineageEdge,
    LineageGraph,
    LineageNode,
    NodeType,
)
from forkit_core.schemas import (
    AgentArchitecture,
    AgentTaskType,
    Architecture,
    LicenseType,
    PassportStatus,
    TaskType,
)
from forkit_core.schemas._compat import _validate_hash

# ── colour helpers ─────────────────────────────────────────────────────────────

RESET = "\033[0m"
BOLD = "\033[1m"
GREEN = "\033[92m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
GREY = "\033[90m"
RED = "\033[91m"


def hdr(n: int, title: str) -> None:
    print(f"\n{BOLD}{BLUE}{'─'*62}{RESET}")
    print(f"{BOLD}{BLUE} Use case {n}: {title}{RESET}")
    print(f"{BOLD}{BLUE}{'─'*62}{RESET}")


def ok(msg: str)   -> None: print(f"  {GREEN}✓{RESET}  {msg}")
def info(msg: str) -> None: print(f"  {CYAN}→{RESET}  {msg}")
def warn(msg: str) -> None: print(f"  {YELLOW}!{RESET}  {msg}")
def kv(k: str, v: str) -> None: print(f"  {GREY}{k:<22}{RESET} {v}")


# ── shared fixture ─────────────────────────────────────────────────────────────

CREATOR = {"name": "Example Maintainer", "organization": "Example Lab"}

print(f"\n{BOLD}forkit-core demo  "
      f"{'(Pydantic v2)' if _PYDANTIC_AVAILABLE else '(pure-Python compat)'}{RESET}")

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

kv("Passport ID",  base_model.id)
kv("Short ID",     base_model.short_id() + "...")
kv("Name",         base_model.name)
kv("Version",      base_model.version)
kv("Task type",    str(base_model.task_type.value))
kv("Architecture", str(base_model.architecture.value))
kv("License",      str(base_model.license.value))
kv("Creator",      f"{base_model.creator.name} / {base_model.creator.organization}")
kv("Parameters",   f"{base_model.parameter_count:,}")
kv("Status",       str(base_model.status.value))
kv("artifact_hash",str(base_model.artifact_hash))
kv("parent_hash",  str(base_model.parent_hash))
ok(f"Base model registered — ID: {base_model.short_id()}...")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 2 — Register a fine-tuned model with parent_hash provenance
# ══════════════════════════════════════════════════════════════════════════════

hdr(2, "Register a fine-tuned model (parent_hash provenance)")

with tempfile.NamedTemporaryFile(suffix=".safetensors", delete=False) as wf:
    wf.write(b"[simulated fine-tuned model weights]" * 1000)
    weights_path = wf.name

weights_hash = H.hash_file(weights_path)
info(f"Hashed weights file  → {weights_hash[:20]}...")

parent_weights_hash = H.hash_string("base-llama-3-8b-weights-v1")

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

kv("Passport ID",  fine_tuned.id)
kv("artifact_hash",fine_tuned.artifact_hash[:20] + "...")
kv("parent_hash",  fine_tuned.parent_hash[:20] + "...")
kv("base_model",   fine_tuned.base_model_name)
kv("ft method",    fine_tuned.fine_tuning_method)
assert fine_tuned.artifact_hash == weights_hash
assert fine_tuned.parent_hash   == parent_weights_hash
ok("Fine-tuned model registered with verifiable hash chain")
ok("Parent hash links back to base model weights without a registry")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 3 — Register an agent passport linked to a model
# ══════════════════════════════════════════════════════════════════════════════

hdr(3, "Register an agent passport linked to a model")

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
kv("Name",         support_agent.name)
kv("task_type",    str(support_agent.task_type.value))
kv("architecture", str(support_agent.architecture.value))
kv("model_id",     support_agent.model_id[:20] + "...")
kv("license",      str(support_agent.license.value))
kv("tools",        str([t.name if hasattr(t, "name") else t["name"]
                        for t in support_agent.tools]))
kv("temperature",  str(support_agent.temperature))
ok("Agent registered — model link is a full 64-char passport ID")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 4 — artifact_hash drives the passport ID
# ══════════════════════════════════════════════════════════════════════════════

hdr(4, "artifact_hash drives the passport ID")

_base = dict(name="same-model", version="1.0.0",
             task_type=TaskType.TEXT_GENERATION,
             architecture=Architecture.DECODER_ONLY,
             creator=CREATOR)

m_no_hash  = ModelPassport(**_base)
m_hash_a   = ModelPassport(**_base, artifact_hash="a" * 64)
m_hash_b   = ModelPassport(**_base, artifact_hash="b" * 64)
m_hash_a2  = ModelPassport(**_base, artifact_hash="a" * 64)

info("Same name / version / creator — different artifact_hash values")
kv("no hash   → ID", m_no_hash.short_id()  + "...")
kv("hash=aaa  → ID", m_hash_a.short_id()   + "...")
kv("hash=bbb  → ID", m_hash_b.short_id()   + "...")
kv("hash=aaa  → ID", m_hash_a2.short_id()  + "... (repeat)")

assert m_no_hash.id != m_hash_a.id,  "no-hash vs hash-a must differ"
assert m_hash_a.id  != m_hash_b.id,  "hash-a vs hash-b must differ"
assert m_hash_a.id  == m_hash_a2.id, "same artifact_hash must be deterministic"
ok("IDs differ when artifact_hash differs")
ok("ID is deterministic: same artifact_hash always → same ID")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 5 — Hash a real artifact directory → attach to passport
# ══════════════════════════════════════════════════════════════════════════════

hdr(5, "Hash a real artifact file → attach to passport")

with tempfile.TemporaryDirectory() as model_dir:
    Path(model_dir, "model.safetensors").write_bytes(b"[weights data]" * 5000)
    Path(model_dir, "config.json").write_text('{"hidden_size": 4096, "num_heads": 32}')
    Path(model_dir, "tokenizer.json").write_text('{"version": "1.0"}')
    Path(model_dir, "README.md").write_text("# Model card (not hashed)")

    info("Model directory contents:")
    for f in sorted(Path(model_dir).iterdir()):
        kv(f"  {f.name}", f"{f.stat().st_size:,} bytes")

    artifact_h        = H.hash_artifact(model_dir)
    weights_only_h    = H.hash_model_artifact(model_dir, include_config=False)
    info(f"hash_artifact(dir)     → {artifact_h[:24]}...")
    info(f"weights only           → {weights_only_h[:24]}...")

    passport_with_hash = ModelPassport(
        **_base,
        artifact_hash = artifact_h,
        quantization  = "fp16",
    )
    kv("Passport ID",   passport_with_hash.id)
    kv("artifact_hash", passport_with_hash.artifact_hash[:24] + "...")

    assert H.verify_artifact(model_dir, passport_with_hash.artifact_hash)
    ok("Artifact hash verified — model directory matches passport")

    # Tamper: overwrite weight file
    Path(model_dir, "model.safetensors").write_bytes(b"[TAMPERED weights]" * 5000)
    tampered_h = H.hash_artifact(model_dir)
    assert tampered_h != artifact_h
    warn("After tampering with weights → hash MISMATCH detected")
    ok("Integrity check catches model tampering")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 6 — Fork an agent (parent_hash chain)
# ══════════════════════════════════════════════════════════════════════════════

hdr(6, "Fork an agent — parent_hash chain")

parent_config       = {
    "system_prompt_hash": H.hash_system_prompt("You are a support agent."),
    "tools":              sorted(["kb_search", "ticket_create"]),
    "temperature":        0.3,
}
parent_config_hash  = H.hash_config(parent_config)

parent_agent = AgentPassport(
    name          = "support-agent-en",
    version       = "1.0.0",
    model_id      = fine_tuned.id,
    task_type     = AgentTaskType.CUSTOMER_SUPPORT,
    architecture  = AgentArchitecture.REACT,
    creator       = CREATOR,
    artifact_hash = parent_config_hash,
)

forked_config      = {
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

kv("Parent agent ID",  parent_agent.short_id() + "...")
kv("Parent art. hash", parent_agent.artifact_hash[:20] + "...")
kv("Forked agent ID",  forked_agent.short_id() + "...")
kv("Forked art. hash", forked_agent.artifact_hash[:20] + "...")
kv("parent_hash",      forked_agent.parent_hash[:20] + "...")
kv("fork_reason",      forked_agent.fork_reason)

assert forked_agent.parent_hash == parent_agent.artifact_hash
ok("parent_hash == parent agent's artifact_hash — verifiable without a registry")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 7 — Trace lineage: ancestors + descendants
# ══════════════════════════════════════════════════════════════════════════════

hdr(7, "Trace lineage: ancestors and descendants")

g = LineageGraph()

for p in (base_model, fine_tuned):
    g.add_node(LineageNode(p.id, NodeType.MODEL, p.name, p.version))
for a in (support_agent, parent_agent, forked_agent):
    g.add_node(LineageNode(a.id, NodeType.AGENT, a.name, a.version))

g.add_edge(LineageEdge(fine_tuned.id,   base_model.id,  EdgeType.DERIVED_FROM, "LoRA fine-tune"))
g.add_edge(LineageEdge(support_agent.id,fine_tuned.id,  EdgeType.BUILT_ON))
g.add_edge(LineageEdge(parent_agent.id, fine_tuned.id,  EdgeType.BUILT_ON))
g.add_edge(LineageEdge(forked_agent.id, parent_agent.id,EdgeType.FORKED_FROM, "Arabic support"))

info(g.summary())
print()

info(f"Ancestors of '{forked_agent.name}':")
for node in g.ancestors(forked_agent.id):
    kv(f"  [{node.node_type}]", f"{node.name} v{node.version}")

print()
info(f"Descendants of '{base_model.name}':")
for node in g.descendants(base_model.id):
    kv(f"  [{node.node_type}]", f"{node.name} v{node.version}")

ok("Full lineage graph traversal complete")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 8 — Verify passport integrity
# ══════════════════════════════════════════════════════════════════════════════

hdr(8, "Verify passport integrity")

orig_dict = fine_tuned.to_dict()
info("Verify original passport — re-derive ID from canonical fields:")

# Strip id so it is re-computed from scratch
stripped = {k: v for k, v in orig_dict.items() if k not in ("id", "passport_type")}
recomputed = ModelPassport.from_dict(stripped)

kv("Stored ID",     orig_dict["id"][:20] + "...")
kv("Recomputed ID", recomputed.id[:20] + "...")
kv("Match",         str(recomputed.id == orig_dict["id"]))
assert recomputed.id == orig_dict["id"]
ok("Passport integrity verified — re-derived ID matches stored ID")

print()
info("Tamper: change the name field and recheck:")
tampered_dict            = {k: v for k, v in orig_dict.items() if k not in ("id", "passport_type")}
tampered_dict["name"]    = "TAMPERED-name"
tampered               = ModelPassport.from_dict(tampered_dict)

kv("Stored ID",    orig_dict["id"][:20] + "...")
kv("After tamper", tampered.id[:20] + "...")
kv("Match",        str(tampered.id == orig_dict["id"]))
assert tampered.id != orig_dict["id"]
warn("Tampered passport detected — ID mismatch")

# ══════════════════════════════════════════════════════════════════════════════
# USE CASE 9 — Serialise → dict → deserialise roundtrip
# ══════════════════════════════════════════════════════════════════════════════

hdr(9, "Serialise → dict → deserialise roundtrip")

serialised = json.dumps(fine_tuned.to_dict(), indent=2, default=str)
info(f"Serialised to JSON ({len(serialised)} chars)")

restored = ModelPassport.from_dict(json.loads(serialised))
kv("Original ID",  fine_tuned.id[:20] + "...")
kv("Restored ID",  restored.id[:20] + "...")
kv("IDs match",    str(fine_tuned.id == restored.id))
kv("Name match",   str(fine_tuned.name == restored.name))
kv("Hash match",   str(fine_tuned.artifact_hash == restored.artifact_hash))
assert fine_tuned.id == restored.id
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
    ("too short",    "abc123"),
    ("uppercase hex","A" * 64),    # normalised to lowercase → accepted
    ("non-hex chars","z" * 64),
    ("valid hash",   "a" * 64),
]
for label, value in cases:
    try:
        result = _validate_hash(value)
        ok(f"{label:<22} → accepted  ({result[:12]}...)")
    except ValueError as e:
        warn(f"{label:<22} → rejected  ({str(e)[:52]}...)")

# Valid hash must be accepted by ModelPassport
valid_m = ModelPassport(**_base, artifact_hash="a" * 64)
ok("Valid 64-char lowercase hex accepted by ModelPassport")

# Invalid hash must raise
try:
    ModelPassport(**_base, artifact_hash="NOT-A-VALID-HASH")
    print(f"  {RED}✗  Should have raised ValueError!{RESET}")
except ValueError:
    ok("Invalid artifact_hash correctly raises ValueError")

# ── Final summary ──────────────────────────────────────────────────────────────

print(f"\n{BOLD}{GREEN}{'═'*62}{RESET}")
print(f"{BOLD}{GREEN} All 10 use cases completed successfully.{RESET}")
mode = "Pydantic v2" if _PYDANTIC_AVAILABLE else "pure-Python compat"
print(f"{BOLD}{GREEN} Backend: {mode}{RESET}")
print(f"{BOLD}{GREEN}{'═'*62}{RESET}\n")
