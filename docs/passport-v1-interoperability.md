# AI Passport v1 interoperability profile

**Draft for implementation review.** This profile makes the existing [identity specification](identity-spec.md) reproducible across languages. Forkit Core is the reference implementation. A change to the bytes or digest for an existing valid passport requires a new identity version and migration guidance.

## Derive the passport ID

1. Read `passport_type` (`model` or `agent`), `name`, `version`, `creator.name`, and `creator.organization` from the passport. These are Unicode strings, except that a missing or null organization maps to JSON `null`. An empty organization stays an empty string. Preserve the version string as supplied. In this profile it has two or three non-empty ASCII digit components separated by periods, including forms such as `1.0` and `2.00.1`.
2. Serialize a JSON object with keys in this order: `creator_name`, `creator_org`, `name`, `passport_type`, `version`. Use a single space after each comma and colon and no other whitespace outside strings. Inside strings, escape double quotes and backslashes, and leave forward slashes literal. Use the short JSON escapes for backspace, tab, newline, form feed, and carriage return. Escape all other characters outside U+0020–U+007E as lowercase `\u` sequences with four hexadecimal digits. Encode non-BMP characters as two UTF-16 surrogate escapes. Preserve the original Unicode scalar sequence without normalization.
3. If `artifact_hash` is present and non-null, it is a lowercase 64-character SHA-256 hex digest on the wire. Prepend that digest and one ASCII `|` to the JSON string. With an absent or null `artifact_hash`, use the JSON string alone.
4. Compute SHA-256 over the resulting UTF-8 bytes. The 64 lowercase hexadecimal characters are the portable passport `id`. Store the same value as `passport_id` when referencing the passport outside its document.

## Verify and connect a passport

Derive the ID from the received document and compare it with the stored `id`. A missing or different ID fails identity verification. To validate a full passport, also validate its schema and, where the artifact is available, compare its content digest with `artifact_hash`. A matching ID establishes consistency between the stored ID and the identity fields. Claims about the creator or provenance require separate evidence.

Keep timestamps, application metadata, service aliases, lineage references, and account or workspace identifiers out of the ID calculation. A Connect implementation should import and export the same portable ID. The interoperability acceptance test uses synthetic model and agent fixtures, attaches service metadata, exports them again, and checks that Core derives the original IDs and still resolves the lineage links.

## Exchange lineage

Reference a fine-tune's parent with `base_model_id`, an agent's base model with `model_id`, and an agent fork's parent with `parent_agent_id`. Each link uses a passport ID. `parent_hash` refers to the parent artifact digest and serves a separate verification purpose.

A materialized graph uses `nodes` and `edges` arrays. A node carries `id`, `node_type`, `name`, `version`, and optional `metadata`. An edge carries `source`, `target`, `edge_type`, and optional `reason` and `created_at`. Edges point from child to parent.

| Edge type | Source | Target |
| --- | --- | --- |
| `derived_from` | Model | Parent model |
| `built_on` | Agent | Model |
| `forked_from` | Agent | Parent agent |

Materialized graph edges must resolve both endpoints and form a directed acyclic graph. Ancestors follow the edge direction and descendants follow the reverse direction. The vectors include a valid graph. Applying the same constraints when loading graph JSON in Core is tracked in [PR #21](https://github.com/Forkit-Dev-Core/Forkit_Dev/pull/21).

## Run the conformance vectors

[The JSON fixture](../tests/fixtures/passport-v1.json) contains synthetic identity inputs, exact hash preimages and full expected IDs, plus a lineage graph. Each `identity` entry uses a passport identity projection. To check a new implementation, derive and verify each expected ID and exercise the `lineage` query in both directions. Core runs the same vectors with `python -m pytest tests/test_passport_v1.py`.
