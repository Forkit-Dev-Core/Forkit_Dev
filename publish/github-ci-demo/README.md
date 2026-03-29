# Forkit Core GitHub CI Demo

This demo proves that a repository can commit a `forkit-passport.json` file and validate it in GitHub Actions with Forkit Core's reusable validator.

## Files

- `forkit-passport.json`
- `.github/workflows/validate-forkit-passport.yml`

## Copy into another repo

1. Copy `forkit-passport.json` into the repository root.
2. Copy `.github/workflows/validate-forkit-passport.yml` into `.github/workflows/`.
3. Adjust the passport fields to match your own model or agent metadata.
4. Push or open a pull request.

## Expected CI behavior

- Passes when the passport file exists, matches the current `ModelPassport` or `AgentPassport` schema, and stores the correct deterministic `id`.
- Fails when the file is missing, the JSON is invalid, required fields are missing, or the stored `id` no longer matches the passport content.

## Run locally

From a Forkit Core checkout:

```bash
python scripts/validate_passport.py --path publish/github-ci-demo/forkit-passport.json
```

Expected output:

```text
Forkit passport is valid
```

If you are copying this into another repository, keep the same local target path and update the workflow input only if you rename `forkit-passport.json`. After the first tagged release exists, prefer pinning the reusable action to a release tag instead of `@main`.
