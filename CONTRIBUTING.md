# Contributing to Forkit Core

Forkit Core is the **local-first, independent Apache-2.0 AI Passport identity layer**.
It is separate from Footprints (AI discovery) and from hosted AI Passport Connect.
Contributions here must not require hosted Forkit accounts, production secrets, or private services.

## First contribution

1. Pick an issue (prefer `good first issue` or the hackathon challenge label), comment that you are working on it, and fork this repository.
2. Create a focused branch: `git switch -c fix/short-description`.
3. Set up a Python 3.10+ environment and run:

   ```bash
   python -m pip install -e ".[dev]" build
   ruff check .
   pytest
   python -m build
   ```

4. For UI changes, install Node 20+ and run:

   ```bash
   cd web
   npm ci
   npm run lint
   npm run build
   ```

5. Push your fork branch and open a pull request against `main`. Link its issue, explain actual behavior, include before/after tests and redacted screenshots when useful. A maintainer reviews and merges; do not push directly to `main`.

## Contract and privacy boundaries

- Treat identity derivation, canonical serialization, hashes, schema semantics, verification, lineage, registry and sync envelope shape as **high-risk contracts**. Propose these changes in an issue first and preserve regression fixtures.
- Never silently rewrite `passport_id`, alter a stored identity field, downgrade verification, or import untrusted lineage/sync data without validation. Identify migrations and backwards compatibility explicitly.
- Do not add hosted login, API keys, remote telemetry, third-party uploads, or production system access. The existing local service must remain local by default.
- Never put credentials, customer records, private repository URLs, real prompts, model weights, local filesystem paths, personal data or internal infrastructure details into issues, tests, commits, screenshots or Actions logs. Use fictitious, deterministic fixtures.
- Prototype UI results must be labelled when simulated. A green check confirms deterministic consistency, **not** safety, ownership, legal approval, or truthful provenance.
- A new framework adapter must be optional, with its external dependency in a corresponding extra; keep base Python usage dependency-free.

## Review checklist

- [ ] One PR for one change, with a linked issue and tests for positive, negative, malformed and repeated inputs as applicable
- [ ] No change to stable IDs without explicit maintainer sign-off and identity specification update
- [ ] No secret, private integration, or personal data exposure
- [ ] `ruff check .` and `pytest` run; package and frontend checks run if applicable
- [ ] Docs, examples, and migration notes reflect actual current behavior

Security vulnerabilities must be reported privately as described in [SECURITY.md](SECURITY.md), not as public issues. By submitting a contribution, you represent that you may license it under Apache-2.0; you retain any rights not granted under that license.
