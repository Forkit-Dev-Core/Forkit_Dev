# Security Policy

## Supported scope

Security issues in the open source core include:

- deterministic identity verification errors
- local registry tamper-detection failures
- sync contract flaws in the OSS server or bridge
- local MCP, CLI, SDK, or server behaviors that expose sensitive data unexpectedly

The latest `main` branch is the primary supported security target. Once versioned releases are published, the latest release tag should be treated as the stable support line.

## Reporting a vulnerability

Please do not post full exploit details in a public issue first.

Use GitHub's private vulnerability reporting for this repository if it is enabled. If private reporting is unavailable in your environment, open a minimal public issue asking maintainers for a secure reporting path and avoid including secrets, tokens, or weaponized proof-of-concept details.

## What to include

- affected commit, tag, or branch
- exact local setup and commands used
- minimal reproduction steps
- impact on deterministic identity, offline/local-first behavior, or data integrity
- whether the issue affects only local use or also the sample HTTP or MCP surfaces

## Response expectations

Maintainers will triage reports based on reproducibility, impact, and whether the issue affects the open source core. Fixes may land first on `main` before a tagged release is cut.
