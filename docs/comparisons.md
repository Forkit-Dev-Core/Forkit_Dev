# Why Forkit Dev Core Exists

Forkit Dev Core is not a replacement for every metadata file. It exists to cover a specific gap: deterministic identity and locally verifiable lineage for AI models and agents.

## Forkit Dev Core vs plain model cards

Model cards are useful for narrative documentation, usage guidance, and disclosure.

Forkit adds:

- deterministic `passport_id` derivation
- local verification that the stored passport still matches its identity
- machine-readable lineage between models and agents
- local registry, CLI, SDK, CI validation, and MCP tooling around the same document contract

Model cards still matter. Forkit can complement them, and this repository already includes a local exporter for Hugging Face-style model cards.

## Forkit Dev Core vs plain metadata JSON

A plain JSON file can describe a model or agent, but by itself it does not define:

- which fields form identity
- how to verify drift or tampering
- how lineage should link between derived models and agents
- how local tooling should query, validate, or sync the document

Forkit keeps the format file-based and simple, but adds a deterministic identity contract and local tooling around it.

## Forkit Dev Core vs local registries without deterministic identity

A local registry can store records, but storage alone does not guarantee stable identity. Two records with similar metadata can drift or be overwritten without a portable verification rule.

Forkit focuses on:

- deterministic identity from defined passport fields
- file-backed local storage
- verifiable lineage edges
- portable sync envelopes that do not require a shared database

## Forkit Dev Core vs spreadsheets or manual tracking

Spreadsheets are useful for planning and lightweight inventory, but they are hard to validate programmatically and easy to drift away from the runtime reality of a model or agent.

Forkit is better suited when you need:

- a machine-readable contract checked in CI
- reproducible local verification
- agent-to-model lineage that can be inspected by code
- adapters and tooling that work on the same local documents

## What Forkit does not claim

Forkit Dev Core does not try to be:

- a hosted governance platform
- a policy engine for enterprise approval chains
- a universal registry for every AI lifecycle workflow

It is intentionally narrower: portable passports, local verification, lineage, sync contracts, adapters, and developer tooling.
