# Contributing to Forkit Dev Core

Forkit Dev Core is the local-first, open source core of Forkit. Contributions should improve portable passports, deterministic identity, lineage, sync contracts, adapters, developer tooling, or local verification.

## Scope

Please keep changes in scope for the OSS core.

In scope:

- deterministic `passport_id` derivation and verification
- local JSON or SQLite registry behavior
- local HTTP service, CLI, SDK, examples, and docs
- local adapters and MCP tooling
- sync/export contracts that work without a hosted dependency

Out of scope for this repository:

- SaaS dashboards or hosted auth
- enterprise approval chains or org admin workflows
- features that require Forkit-hosted infrastructure to be useful

## Development Setup

```bash
git clone https://github.com/arpitasarker01/Forkit_Dev.git
cd Forkit_Dev
pip install -e ".[dev]"
```

Run the checks you touched:

```bash
pytest
python -m build
```

Useful local examples:

```bash
python examples/minimal_local_passport.py
python examples/cli_quickstart.py
python examples/mcp_quickstart.py
python examples/tamper_detection_demo.py
```

## Change Expectations

- Check what already exists before adding a new path or abstraction.
- Preserve deterministic identity behavior unless the change is explicitly justified and versioned.
- Preserve offline-first and local-first behavior.
- Prefer small, surgical edits over rewrites.
- Keep examples runnable and aligned with real repository behavior.
- If you touch packaging, docs, or workflows, verify they still build locally.
- Preserve `forkit.*` as the canonical import path and keep any touched `forkit_core.*` compatibility shim working.

## Pull Requests

Before opening a PR:

- explain the user-facing or developer-facing problem clearly
- describe how you validated the change
- call out any manual GitHub or PyPI settings maintainers still need to do
- update docs or examples when commands or behavior change

Use the PR template checklist so maintainers can review scope quickly.
