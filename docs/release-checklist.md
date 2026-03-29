# Release Checklist

This checklist is for preparing Forkit Dev Core for a public Python release without changing the local-first contract.

## Before tagging

1. Update the package version in [`forkit/__init__.py`](../forkit/__init__.py).
2. Review [`CHANGELOG.md`](../CHANGELOG.md) and release notes.
3. Run local validation:

```bash
pip install -e ".[dev]"
pytest
python -m build
```

4. Smoke-test the documented adoption paths:

```bash
python examples/minimal_local_passport.py
python examples/cli_quickstart.py
python examples/github_ci_quickstart.py
python examples/mcp_quickstart.py
python examples/tamper_detection_demo.py
```

5. Confirm README, docs, and community files still match current behavior.

## GitHub and package-index setup

These settings are required once per repository or index. They are not handled by this repository automatically.

1. Create GitHub environments named `testpypi` and `pypi`.
2. Configure a Trusted Publisher on TestPyPI for this repository and workflow:
   - workflow file: `.github/workflows/release-publish.yml`
   - environment: `testpypi`
   - tag pattern used by this repo: `testpypi-v*`
3. Configure a Trusted Publisher on PyPI for the same workflow:
   - workflow file: `.github/workflows/release-publish.yml`
   - environment: `pypi`
   - tag pattern used by this repo: `v*`

## Tag conventions

- `testpypi-vX.Y.Z` publishes to TestPyPI
- `vX.Y.Z` publishes to PyPI

The workflow only builds and publishes on tags. It does not publish on branch pushes.

## After tagging

1. Verify the GitHub Actions run built artifacts successfully.
2. Verify the uploaded version on TestPyPI or PyPI.
3. Install the released package in a clean environment and run one quick smoke test:

```bash
python -m pip install forkit-core
python -c "from forkit import __version__; print(__version__)"
```

4. If the release is good, create or update the GitHub release notes.
