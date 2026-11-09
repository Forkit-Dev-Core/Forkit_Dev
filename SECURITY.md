# Security Policy — Forkit Core

## Supported releases

The supported open-source line is `v0.1.x` (alpha). The local-first Core does **not** certify model safety, provenance truth, ownership, or legal compliance.

## Private vulnerability reporting

**Do not disclose a vulnerability in a public issue, PR, discussion or hackathon presentation.** Send a private report to **info@forkit.dev**. If GitHub private vulnerability reporting is enabled in repository settings, that option may also be used; this document does not claim it is enabled.

Include an affected commit/version, impact, and minimal steps using synthetic data. Never send active tokens, personal machine logs, real customer passports, prompts, passwords, or production details.

We will investigate privately before coordinating a public advisory. No automated response-time guarantee is made.

High-risk areas include ID/canonicalization, lineage loading, sync receiver input, local API binding, dependency and GitHub Actions supply chain, and inadvertent data disclosure. Fork PR workflows should have read-only `GITHUB_TOKEN` permissions and no production credentials.
