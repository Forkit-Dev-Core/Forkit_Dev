# macOS developer beta — 0.1.0b5

The native Apple Silicon app bundles Python 3.11 and Git. Local installation,
receipts, Passport creation, Today, unlimited-time history and cards need no
Forkit account. The separate CLI ZIP needs Python 3.11, venv/pip and Git.

Install once, restart the coding tool and review its official hooks once. Codex
is the primary adapter; Claude Code and Cursor remain experimental. Existing
configuration is preserved and Forkit removes only its own recorded hooks.
`setup --disable` stops capture without deleting history. Tools installed later
need another setup pass. Hook configuration is not proof that the tool trusted it.

## What is validated

One physical Apple Silicon Mac: 1,010 tests and controlled offline installation,
update/rollback, callback capture, two-session history and local card generation.
Native runtime checks deny network access, host Python, developer tools and system
Git. The user reviewed the supplied-logo preview, replay and PNG export. These
checks are development evidence, not independent customer acceptance.

## Limits before wider promotion

- **Distribution:** the app is ad-hoc signed, not Developer ID signed/notarized.
  A downloaded app may be blocked by macOS. Validate a freshly downloaded package
  on another Mac before promising a frictionless installation. Do not disable
  Gatekeeper or strip quarantine as an installation instruction.
- **Fresh permissions:** another Mac/OS user and Files & Folders allow/deny/revoke
  flows remain unvalidated. Do not require blanket Full Disk Access.
- **Timing:** duration is elapsed time including idle/sleep. Codex captures a
  conversation session, not each reply. Completion can wait for archive, exit or
  idle finalization. Missing ends remain recoverable with unknown timing.
- **Scope:** one active capture per Git root; up to 2,000 supported project files.
  Overlapping human/agent work cannot be exclusively attributed. Remote sessions,
  model runtime calls and unsupported formats are not observed automatically.
- **Performance:** busy/cold-machine, sleep/wake and full native opening acceptance
  remain. Do not translate controlled benchmarks into production latency promises.
- **History:** no time-based signup gate; the 64 MiB store cap still applies, with
  explicit maintenance/backup controls. Website registration and receipt sync are
  optional future integrations, not required local features.

Intel Mac and Windows have no validated package. Linux ARM64 is a separate CLI
path, not this native app; b5 Linux x86_64 validation is pending.

See [Apple's app security guidance](https://support.apple.com/en-gb/102445) and
[the capture adapter guide](CAPTURE.md).
