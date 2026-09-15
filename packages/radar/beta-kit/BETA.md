# Forkit Session Receipt — CLI developer beta b6

You vibe code. Forkit remembers what changed.

The candidate supports Apple Silicon Mac with Python 3.11/Git, and Ubuntu ARM64
with Python 3.12/venv/pip/Git. Native Mac archives are withheld. Intel Mac, Windows
and new Linux x86_64 have no validated package. Outside-user acceptance remains.

Extract the matching ZIP, run `sh install.sh --check`, then
`sh install.sh --no-app`. Installation refuses existing locations. Use `--prefix`
and `--bin-dir` for a separate upgrade destination; preserve your old install and
private store until the new one is checked. No Forkit account is required.

Review installed hooks in the coding tool, restart it and open the actual Git
repository, not a parent folder. Start and finish a new session. For Codex the
boundary is the conversation lifecycle, not each reply; archive/normal close or
idle finalization can be required. Wrapper fallback:

```sh
~/.local/bin/forkit-radar session run --tool codex -- codex
~/.local/bin/forkit-radar open
```

Repeat `open` after another captured session. History shows retained receipts;
Latest shows only the newest one. Local history is free without a time gate,
subject to the documented 64 MiB store cap and backup/maintenance controls.

Optional tool activity is experimental and off by default:

```sh
~/.local/bin/forkit-radar setup --activity
# Review changed hooks and begin a new session.
~/.local/bin/forkit-radar setup --no-activity
```

Supported tool categories, hostname destinations when exposed and reported
outcomes stay local. Read CAPTURE.md for exact agent coverage. This does not
observe all API traffic, script-internal requests or personal browser history.
Prompts, query strings, URL paths, headers and results are not retained. Tool
success is not independently verified network success. Activity is excluded from
share cards, public reporting, change counts and Passport-version counts.

Try two real coding sessions: verify one changed file and supported metadata
against your work, then check the previous-session comparison. A day or week of
waiting is unnecessary. No questionnaire is required. Hook callbacks tested in
isolation are not the same as actual application acceptance; Claude Code and
Cursor remain experimental. The change map replays changed areas, not actual
network crossings, edit chronology or authenticated AI authorship.

Cards are local exports; review before sharing. Optional count reporting is a
separate opt-in described in USAGE.md. No adoption numbers are bundled.
