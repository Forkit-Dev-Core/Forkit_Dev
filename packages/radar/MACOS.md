# Mac CLI beta — b6

This release supplies the CLI only. It requires Apple Silicon, Python 3.11 with
venv/pip and Apple's Git. Use `sh install.sh --no-app`. Native archives are withheld.
No certificate bypass, quarantine removal or Full Disk Access is required.
Optional activity capture is experimental and requires explicit `setup --activity`
and review of the changed hook definitions in your coding tool. No network audit,
personal browsing, model-provider traffic or arbitrary script requests are claimed.

Install once, restart the coding tool and review its official hooks once. Codex
is the primary adapter; Claude Code and Cursor remain experimental. Existing
configuration is preserved and Forkit removes only its own recorded hooks.
`setup --disable` stops capture without deleting history. Tools installed later
need another setup pass. Hook configuration is not proof that the tool trusted it.

## What is validated

One physical Apple Silicon Mac: 1,033 automated tests passed for b6. Fresh CLI
bundle installation, controlled hook callbacks and retained history are checked
separately. Previous native-app and preview checks do not qualify a b6 native app
for release. These checks are development evidence, not independent customer
acceptance. New activity hooks still need review and real application acceptance.

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
path, not this native app; Linux x86_64 validation is pending.

See [Apple's app security guidance](https://support.apple.com/en-gb/102445) and
[the capture adapter guide](CAPTURE.md).
