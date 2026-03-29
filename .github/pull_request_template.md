## Summary

Describe the change in one or two sentences.

## Validation

- [ ] `pytest`
- [ ] `python -m build`
- [ ] Relevant example or manual command still runs locally

## Scope Check

- [ ] Deterministic passport identity behavior is unchanged, or the change is explicitly justified
- [ ] Offline-first and local-first behavior is preserved
- [ ] No hosted dependency or SaaS workflow was introduced
- [ ] `forkit.*` imports still work, and any `forkit_core.*` compatibility touched by this PR still works
- [ ] Docs and examples are updated if user-visible behavior changed

## Notes

Call out any manual GitHub, PyPI, or release settings that maintainers must update separately.
