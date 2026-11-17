## Summary and linked issue

What changes, which issue does it close, and what observable problem does it solve?

## Impact / boundary

- [ ] Local-first Core only; no dependencies on Footprints, private Forkit Connect, or production infrastructure
- [ ] No secrets, prompts, customer data, personal paths/logs, or internal URLs in changes, fixtures or screenshots
- [ ] No new authentication, outbound telemetry, privileged access or remote-write behavior
- [ ] Identity, versioning, canonical serialization and persisted compatibility **unchanged**; OR explain exact change, migration, tests and maintainer approval below

**Contract or backwards-compatibility impact:** None / explain here.

## Validation

- [ ] `ruff check .`
- [ ] `pytest`
- [ ] `python -m build` if packaging or install docs changed
- [ ] `cd web && npm ci && npm run lint && npm run build` if UI changed
- [ ] New tests include negative/invalid or adversarial input cases where relevant
- [ ] README/spec/changelog updated for user-visible or contract changes

## Evidence

Safe reproduction instructions, before/after output and (redacted) screenshots, as applicable. Never attach genuine customer or personal device evidence.
