# Forkit Session Receipt — short developer beta

**You vibe code. Forkit remembers what changed.**

Finish a supported coding session, inspect the receipt, open **Today**, and save a
card if it is useful. After your next session the new comparison is available;
tomorrow, check Today again. Weekly history is an extra, not a waiting period.
All local history stays free without signup. Website Passport registration/sync is
optional future work; it is not available in this offline beta.

## Choose the matching package

| Platform | Path | Scope |
| --- | --- | --- |
| macOS Apple Silicon | Native app with bundled Python/Git; or separate Python 3.11 CLI ZIP | Primary developer beta. One physical Mac tested; broader OS/fresh-user and signed download acceptance remain. |
| Linux ARM64 | Python 3.12 CLI ZIP and offline HTML view | Local Ubuntu 24.04 ARM64 VM validation is recorded in the release audit. No native Linux GUI. |
| Linux x86_64 | Python 3.12 CLI release workflow | Older public b3 passed Ubuntu 24.04 x86_64. The new b5 needs its own x86_64 CI evidence before this build is advertised there. |
| Intel Mac / Windows | No supported package in this candidate | Not validated. Do not substitute another architecture’s ZIP. |

These are candidate delivery paths, not a claim that b5 is already public. The
public b3 release is older and has a hook-ended share-card bug fixed in this source.
Do not use b3 to demonstrate the new native app, logo/map or count policy.

## First useful result

Mac native: open the reviewed app, let it install to your user Applications folder,
review Forkit hooks in Codex’s `/hooks`, then start a new Git-project session.
For the CLI ZIP, extract it and run `sh install.sh --check`, then `sh install.sh`.
The CLI needs the exact Python minor version shown in README.txt, plus Git and
venv/pip. It refuses existing install locations rather than overwriting them.

No repository connection or Forkit login is required. The coding tool may need its
own account. If it was installed after Forkit, rerun `forkit-radar setup`.

1. Finish a real coding session and open Forkit / run `forkit-radar receipt`.
2. Check one file change and one supported dependency/configuration change against
   what you actually did. Report missing/duplicate results as bugs; never upload
   private receipt JSON or project content publicly.
3. Open Today / run `forkit-radar summary`. Save a local card with
   `forkit-radar card --output receipt-card.html`; open it to save PNG.
4. Continue your next session normally, then inspect the new receipt and history.
   A same-day second session gives immediate usefulness; another day can show a
   return. No questionnaire is required.

Codex official lifecycle capture is the primary adapter. It measures the session
boundary, not each reply. Desktop completion may await archive/app exit or idle
finalization. Claude Code and Cursor adapters are experimental; Cursor’s start is
fire-and-forget and its receipts remain partial. Use the explicit wrapper
`forkit-radar session run --tool codex -- codex` for a command boundary, and manual
start/stop only when hooks/wrapping are unavailable. Read the included CAPTURE.md.

The map replays recorded changed areas, not a live route, edit chronology, network
crossings or proof that the AI authored every change. Model/runtime values are
only detectable declarations. Unsupported data stays unknown. Local history has
no time gate; the 64 MiB per-store cap and explicit backup/compaction controls apply.

Optional counts are separate and stay off until consent after the first useful
receipt. See [USAGE.md](USAGE.md). No real adoption numbers are bundled.
