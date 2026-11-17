# Maintainer checklist for a globally accessible, local-first Forkit Core

Maintainers should verify these recommendations in GitHub **Settings** before a contribution event. Merge after required checks pass.

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

## Contribution events

- Scope beginner tasks to identity validation, local CLI usability, lineage reliability, docs/examples and tests; cap proposed changes to reviewable PRs.
- Make one issue per task with a starting file, expected output, and acceptance criteria.
- Review contract and privacy changes and require CI on the proposed commit before merging.

## Ownership and next contribution cycle

Maintainer contacts are [arpitasarker01](https://github.com/arpitasarker01) and [syedofc](https://github.com/syedofc), as listed in CODEOWNERS. For each issue, record the contributor and reviewing maintainer; confirm acceptance before treating a suggested owner as assigned. For releases, record a release owner and a verifier before building.

Forkit Core provides the local AI Passport engine. [Footprints](https://github.com/Forkit-Dev-Core/footprints) provides a separate local interface for discovery and passport workflows. Keep public examples reproducible and synthetic, and keep customer information, business plans, private integrations, and personal device evidence out of commits and public discussions. Participation is open globally and does not require a commercial account.

Prioritize small contributions with explicit acceptance criteria. Existing issues cover CLI output and errors, identity validation, and lineage behavior; check their current status and reproduce on main before starting. Identity and lineage changes need a maintainer review of compatibility, not just a passing test. Documentation, accessible explanations, and synthetic fixtures are also welcome.

Preserve authorship and attribution when adapting a contribution. A superseded PR should link to its replacement and explain what remains. Use a merge method that preserves original contributor commits when their ancestry is part of the agreed credit; do not squash them by default.

For the next Footprints preview, track the Core pin and source-archive hash update in a separate PR. Verify compatibility and build provenance against the exact merged source, then repeat the packaged Windows launcher test. Existing releases remain immutable.

A cleanup of current files does not certify historical commits or release assets. Keep an inventory of any sensitive findings privately; coordinate credential revocation, invite invalidation, and any history rewrite separately. Do not publish the sensitive values in a cleanup issue. History rewrites need an explicit plan for affected refs, contributor coordination, releases, and caches.
