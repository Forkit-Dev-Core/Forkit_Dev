# Maintainer checklist for a globally accessible, local-first Forkit Core

These are **recommendations**, not GitHub settings already applied. Maintainers must verify them in GitHub **Settings** before the hackathon. Do not merge into `main` until required checks run and pass.

## Repository rules (highest priority)

Open **Settings → Rules → Rulesets → New branch ruleset** for branch `main` (or **Settings → Branches → Add branch protection rule** if that is what the account exposes):

- Require a pull request before merging; **1 approval** from someone other than the author.
- Require review from CODEOWNERS for sensitive source paths; existing `CODEOWNERS` lists the two Forkit maintainers.
- Dismiss stale approvals when new code changes arrive; require resolution of review conversations.
- Require status checks to pass, initially **OSS CI / python**, **OSS CI / web**, and **Validate Forkit passport / validate-example-passport** *only after those exact job names have produced green checks*. This patch makes all three jobs run on every PR, including docs-only changes, so required checks cannot be skipped.
- Block force pushes and deletions, including administrator bypass when feasible; do not allow direct pushes to `main`.
- Keep automatic merging disabled. Prefer squash merge and automatically delete completed PR branches.

## Actions / security

- Under **Settings → Actions → General**, set default workflow token permission to **read repository contents**, do not expose production secrets, and avoid privileged `pull_request_target` execution of untrusted fork code.
- For first-time fork contributors, review PR code and approve workflow runs individually if GitHub marks them `action_required`. **Do not lower the global security approval policy** just to make hackathon PRs convenient.
- Check **Settings → Security & analysis** and enable Dependabot alerts, dependency graph, secret scanning/push protection, and private vulnerability reporting where available. Configure CodeQL or another static scan once CI is healthy.
- Keep Actions pinned to maintained versions and consider immutable action SHAs for higher assurance. Review third-party workflow dependencies before adding them.

## License / governance

- This repository has declared **Apache-2.0**, not MIT. Keep the full Apache License text in `LICENSE`, original attribution in `NOTICE`, and `pyproject.toml` / README declarations consistent.
- Confirm company and contributor permission to distribute all committed code/assets before asserting a company owns third-party contributions. Audit the public Git history and image assets separately; this checklist does **not** certify them.
- Keep `SECURITY.md`, `CONTRIBUTING.md`, `CODEOWNERS`, issue and PR templates discoverable. Use Issues for work, Discussions for questions and private reporting for vulnerabilities.
- Record releases with a signed/tagged commit where practical, release notes and validated install commands; do not advertise PyPI if not live.

## Three-day Core hackathon

- Scope beginner tasks to identity validation, local CLI usability, lineage reliability, docs/examples and tests; cap proposed changes to reviewable PRs.
- Make one issue per task with starting file, expected output and acceptance criteria. Label as `hackathon` and `good first issue` once those labels are created.
- Review and merge only after CI has run on the proposed head, and only after contract/privacy review. Outstanding PRs #17, #18, #20, #21, #22 and #23 are **not** assumed safe merely because the author reported local passes.
- Footprints is a separate **three-hour discovery hackathon**. Do not merge Footprints or private Connect code into Forkit Core.
