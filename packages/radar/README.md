# Optional local tools and destinations — b6 experimental
`~/.local/bin/forkit-radar setup --activity` opts in to supported tool-reported
categories, hostname destinations and outcomes for new official-hook sessions.
Review changed hooks before use. `setup --no-activity` stops future collection.
This is partial tool evidence, not API traffic or a complete browsing history.
No prompts, URL paths/queries, headers or response bodies are retained. Activity
stays out of share cards and public counters. See [coverage and privacy](CAPTURE.md).

# Forkit Radar — local Session Receipt

Automatic capture: see [CAPTURE.md](CAPTURE.md) for install-once user hooks, wrapper fallback and manual recovery. Local features require no Forkit account.

**You vibe code. Forkit remembers what changed during the session.**

Forkit OSS needs no signup, login, account, inference API or cloud connection.
Local session capture, receipts/history, existing local Passport creation and
local share cards work without authentication. Authentication belongs only to explicitly selected future
cloud publishing, sync, cross-device, team/company or GitHub organization features.
Logging into a cloud service does not by itself verify a public Passport.

## Install and get your first receipt

**Local beta candidate 0.1.0b6: immediate receipts, Today by default, branded cards and recorded-change highlights.**
Read the [short beta guide](beta-kit/BETA.md) for the Mac/Linux paths and remaining distribution gates.
The native Apple Silicon app bundles Python and Git; the separate CLI ZIP still needs them.
The existing public b3 download is an older release with a hook-ended card bug. It does not provide this candidate.
Unlimited free local history means no time-based account gate; the 64 MiB store cap still applies.
No new candidate has been uploaded. Read [macOS release limitations](MACOS.md).

Download the matching ZIP from the [Session Receipt 0.1.0b3 release](https://github.com/Forkit-Dev-Core/Forkit_Dev/releases/tag/radar-v0.1.0b3), extract it, and run:

```sh
sh install.sh
```

macOS Apple Silicon needs Python 3.11; Linux x86_64 (Ubuntu 24.04) needs Python 3.12. Both need Git and Python venv/pip. After downloading, installation and local use work offline. Windows and a native signed app are not supported yet. Existing installations are preserved; select a separate `--prefix` and `--bin-dir` to try this release alongside one.

For this candidate, installation sets up detected tools across local Git projects. No repository connection:

```sh
~/.local/bin/forkit-radar setup --status
# Restart Codex; review/trust Forkit in /hooks once. Then start sessions normally.
~/.local/bin/forkit-radar open
~/.local/bin/forkit-radar receipt
~/.local/bin/forkit-radar history
~/.local/bin/forkit-radar summary --period today
~/.local/bin/forkit-radar card --output receipt.html
```

[Capture details and limitations](CAPTURE.md): official Codex lifecycle hooks first; separate experimental Claude Code and Cursor adapters; wrapper and manual fallbacks. This is an observed interval, not proof of AI authorship. Model/runtime claims are limited to detectable declarations; prompts and transcripts are never read by capture hooks.

## Optional usage counts

Reporting stays off until new explicit consent after the first useful receipt.
`forkit-radar usage policy` explains the count-only snapshot. `usage enable`
requires a deliberately chosen HTTPS endpoint and `--consent usage-v3`; it sends
nothing itself. Later normal use may report at most once per 24 hours through a
bounded short-lived worker. No signup, daemon or historical import is required.
Use `usage preview`, `usage disable` and `usage withdraw` to inspect or stop it. The Mac app also has Optional usage counts in its menu. The new policy includes intentional view-days and successful card exports; older usage-v2 consent never upgrades automatically. Read [the exact definitions](beta-kit/USAGE.md).
See [the usage notice](beta-kit/USAGE.md) and
[the operator runbook](collector/USAGE_OPERATOR.md). No public collector is deployed
or enabled by this candidate. Incoming reports are pseudonymous; public totals
are suppressed for small cohorts. They are not total installs or unique people.

## Existing manual aggregate reporting

The separate `metrics` feature is **disabled by default** and never sends automatically. Local install,
sessions, Passport creation, history, diffs and share cards still need no account.

Use only a collector address deliberately supplied by its operator:

```console
forkit-radar metrics status
forkit-radar metrics enable --endpoint https://YOUR-COLLECTOR/api/v1/radar
forkit-radar metrics preview --output contribution-preview.json
# Read the preview. Use its printed SHA-256 to send those exact bytes:
forkit-radar metrics send --preview contribution-preview.json --sha256 PRINTED_SHA256
forkit-radar metrics disable
# Remove a previously sent contribution:
forkit-radar metrics withdraw
```

Pass the same `--store /absolute/private/store` to each metrics command when using
a custom session store. For `scan` and `passport create`, the corresponding flag
is `--metrics-store`. Those operations record counts only after explicit enable.
Unchanged duplicate outputs of one Core Passport ID count once. Older unrecorded
scans/creation operations are not estimated. A private profile stores its generated
update credential separately from session receipts and existing Core identity.

The exact preview includes retained session counts from this UTC calendar week and
the previous three weeks, including receipts from before enable. It contains only
allowlisted counts, dates and a sequence. The request uses a separate random
public profile ID and reporting credential. No private Passport ID, revision hash,
project/file/model/agent name, prompt, source text, chat or existing credential
enters the contribution. Treat the profile as pseudonymous, not anonymous; the
chosen collector receives connection metadata.

`preview` does not send anything. It writes a new private file and refuses
overwrites. `send` checks the complete saved preview digest, destination/profile,
and the collector's sequence/body-digest acknowledgement. Retry an uncertain send
with the **same file and hash**. Identical retries replace nothing and add no count.
Use a new preview to update the latest snapshot. There is no automatic scheduler,
background uploader, account registration or default collector URL.

Disabling stops local reporting collection/sends but does not delete an existing
public contribution. Withdrawal authenticates deletion and keeps its credential
until confirmation so interrupted deletion can be retried. The collector excludes
withdrawn/stale profiles and retains minimal revocation metadata to reject delayed
uploads. A new enable after confirmed withdrawal creates a new independent profile.
Local receipts/Passports remain available. The local operation journal is bounded
at 10000 entries and refuses further previews if it becomes incomplete.

The website distinguishes reporting profiles from total installs, overlapping
model/agent observations from unique systems, and declared local traces from
authenticated AI execution. It shows weekly active Passport references and
repeat-check/reconstruction numerators and denominators. Unknown discovery
categories and missing denominators stay unavailable. At least five current
profiles are required before nonempty public counts are shown; this is not a
guarantee of anonymity or fraud resistance. Validation fixtures are labelled.

The ready-to-integrate collector and counting/retention/proxy details are in
[collector/README.md](collector/README.md). It uses the existing hosted stack's
Express/PostgreSQL interface, with separate tables and credentials; the Python
runtime dependencies are unchanged. The Radar page reads a same-origin public
aggregate endpoint and shows unavailable states when disconnected. No hosted
collector, customer website, account system or package has been deployed in this
step. Production logging/retention, HTTPS routing and source review must be verified
for the actual host before publication.

## Private evolution view and summaries

```console
forkit-radar view --output /absolute/private/session-history.html
forkit-radar view --json
forkit-radar summary --period today
forkit-radar summary --period week --timezone Europe/Berlin
forkit-radar summary --json
forkit-radar summary-card --period week --output /absolute/private/weekly-card.html
```

Open the generated history HTML locally. Latest session, Today, This week and
History show saved receipts, supported file/dependency/MCP/tool/model changes,
selected Passport IDs and versions, before/after observed revisions, coverage and
trace gaps. Search filters the shown timeline. The file is a saved view; generate
a new file after another session. It has no listener, network calls, external
assets, account, login or live project/registry reads. Private receipt JSON can
also be saved from the page. **The private page contains project-relative paths
and identity details; use a separate aggregate card for public sharing.**

Day/week totals use every retained receipt in the selected local store, grouped
by completion time. Weeks start on Monday; IANA timezones use historical DST
rules. Between-capture edits have unknown edit times and are counted when their
receipt finishes. Future-dated receipts remain in history but are excluded from
current day/week totals. Default timeline: latest 200 entries; `--limit 1..1000`
changes display only. `--project-id <local-project-uuid>` selects one exact project.
Bounded verification accepts at most 10,000 receipts and HTML at most 16 MiB; it
fails explicitly on limits rather than silently publishing partial totals.

The separate `summary-card` command produces HTML, SVG or JSON; HTML supports
local browser PNG export. Cards contain counts and fixed labels only. They omit
names, paths, dates, source/metadata bodies, source hashes, credentials and all
private identifiers. The existing SessionCard 1.0 contract is unchanged. The new
SummaryCard 1.0 is a distinct allowlisted contract. No upload or publication occurs.

### What a meaningful change counts

Policy `session-meaningful-changes-v1` groups all changed declarations for one
npm/Python package within an interval into one event, preserving each supporting
declaration. Changed fields of one explicit agent tool/model are grouped by its
local slot; client model/provider settings form one event per source. Other
settings and supported file changes count separately. A manifest file explained
by a supported metadata change is not counted again as a file event. File totals
still show every supported file change. Unsupported manifest changes can remain
file events with partial metadata coverage. This is a deterministic scope policy,
not a semantic assessment of code quality or business importance.

Separate sessions, projects and between-capture intervals remain separate events.
An add followed by a later removal is two observed events. Wider "since a comparable
receipt" comparisons are displayed but never added to these totals again. Gap
events are counted only for adjacent captures in the same selected context;
scope switches or missing predecessor evidence stay visibly unavailable.

### Durable observed history and reconstruction

Session SQLite schema 2 adds compressed canonical observed revisions, immutable
session evolution records and local heads beside the original receipts. SHA-256
domains are `forkit-session-revision-v1`, `forkit-session-receipt-v1` and
`forkit-session-event-v1`, each followed by a newline before RFC 8785 JSON bytes.
These are **private session contracts**, separate from the original signed Radar
manifest/binding contracts. Revisions normalize file/source/fact ordering and
exclude transient diagnostics, excluded-file totals and source locators. Supported
state and measurement completeness remain included. A reversion can repeat a
revision digest while creating a new event; an unchanged session adds a receipt,
not a fictitious new Core Passport version.

A reconstructed event needs retained checked before/after revisions, a matching
receipt, intact predecessor links/heads and a consistent explicitly selected Core
agent/model Passport at both endpoints. Recovered sessions with unknown ending
times and edits between captures do not gain session attribution. Known events
under partial coverage can have complete traces; unobserved edits cannot enter
the denominator. Missing Passport associations remain in the denominator.

Original category/event counts survive missing revision data. Missing/tampered
state or receipt evidence removes its reconstruction claim and invalidates dependent
links. If original event counts cannot be established, the reconstruction rate is
unavailable. JSON rates use integer **basis points** (`10000` = 100%); a zero
denominator is null. Coverage and incomplete-history counts are reported separately.

This reconstructs recorded scoped evolution, not source bodies or prompts. Links
express local **project history and declared Passport associations**. Changing a
selected Passport does not authenticate logical-agent lineage. Copied projects
have separate local project records even when they select the same Passport.
Core identity, local registry/lineage behavior and unsigned enrollment drafts are
unchanged. Events/heads are unsigned, held in the same local store and do not resist
a compromised account or rollback of the entire store. No ownership, runtime,
security or external verification claim follows from local consistency.

Schema 1 history remains readable without writing. The first write upgrades only
an exact recognized schema transactionally; existing receipt bytes are untouched.
No legacy evidence or chain is fabricated retroactively. Back up before upgrading:
older Radar builds cannot read the schema-2 store. New evolution revisions, counts,
links and heads survive `storage compact`; old capture snapshots may still expire
from future baseline selection. Backups include the new records. The 64 MiB bound
remains, with a larger finish-space reservation; retained evidence eventually
requires a new store or a future explicit archival policy, not silent deletion.

## Private beta kit and easier installation

**Version 0.1.0b4 is the local automatic-setup candidate for user validation.**
The public GitHub download still provides b3. Neither is a published PyPI/npm
release, and outside-user results are still pending. The complete
matching kit contains `START_HERE.html`, `USAGE.md`, an offline installer and locked wheels. Local operation needs no Forkit account.

Open `START_HERE.html` after extracting the kit. In that folder:

```console
sh install.sh --check
sh install.sh
```

The shell bootstrap selects an already installed Python matching the kit's exact
minor version. This b4 kit was checked on macOS Apple Silicon/Python 3.11;
changed b4 behavior still needs Linux validation. The published b3 kits support
macOS Apple Silicon/Python 3.11 and Ubuntu x86_64/Python 3.12.
Python with venv/pip and Git remain prerequisites; the kit does
not include those runtimes. The offline installer downloads nothing. On macOS,
`Install.command` is a convenience Terminal launcher, not a signed/notarized app.
Do not disable operating-system security settings; the guide provides the explicit
Terminal command for the reviewed script.

From this complete source checkout, the one-command alternative is:

```console
sh scripts/install_radar.sh
```

It builds Core and Radar locally in an isolated builder and fetches hash-pinned
public Python dependencies. No Forkit package is fetched by name from PyPI. The
existing `python3 scripts/install_radar.py` entry point also works. `--check`
validates prerequisites/destinations and a supplied bundle without installing or
making a network request. It may use a temporary file for bundle-lock comparison.

The default application is `~/.local/share/forkit-radar` and command is
`~/.local/bin/forkit-radar`. Use that full path when it is outside PATH. No global
Python environment, shell profile or existing command is replaced. Existing paths
are refused; failed fresh installs remove their own incomplete application only.
For a parallel candidate installation choose new `--prefix` and `--bin-dir`
locations, and use the full command path printed by the installer. Keep
`~/.forkit-radar` and your Core registry. Installation configures detected tools
once; use `--no-capture` to skip it. On macOS it creates a Finder launcher; use
`--no-app` to skip that. Run `setup --disable` before manually removing Forkit.
There is no automatic updater, uninstaller or reporting opt-in.

Application virtual environments must stay at their installation path; their
[Python runtime and location matter](https://docs.python.org/3/library/venv.html).
Windows and browser-only coding services are outside this kit. Broader architecture
validation and public package/website publication remain separate release work.

## Manual fallback and editor shortcuts

From the root of your existing Git project:

```console
forkit-radar doctor
forkit-radar start --tool cursor
# Work in your editor, then return to the same project:
forkit-radar stop
forkit-radar history
forkit-radar view --output session-history.html
forkit-radar card --output receipt-card.html
```

`doctor` reads setup and local store metadata without scanning source bodies,
starting an agent, writing a session or making a network request. Its optional
`--tool` checks only command availability on PATH, never login or runtime state.
Use `--json` for fixed diagnostic fields without private paths. Successful setup
checks are not authentication or guarantees that every file/metadata format is
supported.

`start` reuses `session start`. `stop` without an ID selects only the exact active
manual session in the selected Git root, using its existing protected project
binding. It never selects the most recent session globally or interrupts a wrapped
command. Pass `--project` and the same `--store` when needed. Explicit
`session stop <id>` and recovery remain available for advanced cases. A replaced,
cloned or moved path does not acquire another project's active session.

Tool choices remain `codex`, `claude-code`, `cursor`, `other`. Choose `other` for
another editor. Tool selection is declared; it does not authenticate AI authorship.
The selected coding tool may have independent account/network requirements.

## Optional count reporting

There is no beta questionnaire in the current onboarding or bundle. Local features
remain account-free. The earlier `metrics` feature is manual and unchanged; its
consent does not activate automatic reporting. The new `usage` commands require
new `usage-v2` consent after an original receipt exists. No endpoint is selected
by default, and no public collector has been deployed by this candidate.

Read [beta-kit/USAGE.md](beta-kit/USAGE.md) for the exact contract, commands,
privacy, retention and measurement limits. The collector implementation and
operator runbook live in `collector/`. Old Prompt 12 questionnaire evidence is
historical; its sample numbers are not adoption.

## Wrapper fallback

After installing, run this from the root of a selected
Git project (or provide `--project /absolute/project`):

```console
forkit-radar session run --tool codex -- codex
forkit-radar receipt
forkit-radar receipt --files
forkit-radar receipt --json
forkit-radar history
forkit-radar card --output receipt.html
```

The explicit wrapper works with a selected command, including `claude` with
`--tool claude-code`. It runs that command interactively, then prints and saves a
receipt. The command's own account/network requirements are independent of Forkit.
No prompts, arguments, terminal output or chat transcripts are recorded. With
`--json`, command stdout goes directly to stderr so receipt stdout remains JSON.
The wrapper preserves the command's exit status and records failures/interruption.
The tool name is your selection, not authenticated software identity or proof
that it authored every edit. The wrapper command does not install hooks. The b4
installer's separate setup configures detected tools unless `--no-capture` is used.

For Cursor, a GUI editor, or any workflow you want to delimit manually:

```console
forkit-radar session start --tool cursor
# Work in your editor. Use the session ID printed by start:
forkit-radar session stop <session-id>
forkit-radar session active
# If an end boundary was lost, explicitly close it as incomplete:
forkit-radar session recover <session-id>
```

Every command accepts `--store /absolute/private-directory`; pass the same value
through the workflow. The parent must exist. Default storage is
`~/.forkit-radar/sessions.sqlite3`, separate from existing enrollment drafts and
Core's registry, reusing Radar's private transactional SQLite connection layer.
Directories/files use 0700/0600. No project commits, stashes, index updates or
source edits are made. Only one active session per selected project/store is
allowed; use `active` then `stop` or `recover` before starting another.

### What a receipt means

- It reports **net endpoint differences observed during the session**. Existing
  dirty edits form the baseline; edits made and reverted between endpoints are
  invisible. Human edits and other concurrent tools can contribute to the result.
- Scope `session-source-files-v1` includes supported source extensions and named
  dependency manifests/lockfiles. Git lists tracked and non-ignored untracked
  paths; Radar safely reads permitted regular files to compute private keyed
  fingerprints. Contents are processed transiently, never persisted or uploaded.
  This explicit session mode extends beyond passive discovery's metadata reads.
- Known secret files/directories, `.env*`, credentials, key files, editor/agent
  private directories, prompt instructions, documentation, binaries, ignored
  untracked files, common build/vendor directories, symlinks and hard links are
  excluded or unknown. This is bounded scope selection, not a secret scanner;
  secrets hardcoded into otherwise permitted source can be read transiently but
  their contents are not stored. Fingerprints never appear in receipt output.
- Captures are bounded to 2,000 supported paths, 4 MiB per file, 64 MiB total file
  bytes, 1 MiB Git output, 5 seconds per Git command and 15 seconds per capture.
  Concurrent file replacement/read failures become unknown. A complete initial
  path inventory is required; incomplete ending inventories cannot manufacture
  additions or removals. Captures are sequential, not atomic filesystem snapshots.
  Each private database is limited to 64 MiB. Writes cannot cross that limit;
  new sessions reserve finish space and stop early when capacity is low. History
  is never automatically deleted. Use the explicit maintenance commands below
  to reclaim old snapshots. Local storage never requires an account.
- Exact, unique content matches are labeled **possible renames**; ambiguous copies
  remain additions/removals. File-change counts count events, with a possible
  rename represented once. Mode changes are included for executable permission.
- Duration uses a same-boot continuous clock including sleep on supported macOS
  and Linux. It is elapsed session time, not active AI time. Recovery after a lost
  end boundary reports unknown duration and includes the interval until recovery.
- Default terminal output omits filenames. `--files` and `--json` are **private
  local output**, not the public aggregate share schema. JSON includes relative
  filenames, but excludes the project root, contents, command arguments and keys.
- New receipts include scoped dependency/config/model changes, optional explicit
  Passport association, and separate previous-session and between-session diffs.
  A source file count is not a count of dependency changes. Existing
  `passport create` and `card` work without an account.

The installed wrapper has been exercised against a controlled editing process;
actual coding-tool and platform probes are recorded in the session audit. Advertise
only the integrations/platforms with recorded real execution evidence. No live AI
authorship, authenticated runtime, security, signed-receipt or release claim follows.

This Session Receipt slice follows the user's revised Prompts 6–9 and account-free
local product requirement. The historical implementation lock remains unchanged;
execution evidence is recorded under `docs/radar-audit/session-step-06/` and
`docs/radar-audit/session-step-07/`, `docs/radar-audit/session-step-08/` and
`docs/radar-audit/session-step-09/`.
This does not complete the old S06–S08 identity/signing milestones.
The lock remains frozen. Publication and real-user pilot results are separate
from local release validation.

### Keep local history usable

```console
forkit-radar storage status
forkit-radar storage backup --output /absolute/private/new-backup.sqlite3
forkit-radar storage compact --keep 20
# Review the preview, then explicitly apply it:
forkit-radar storage compact --keep 20 --apply
```

Compaction retains **every receipt**, every active session baseline and the latest
20 ending snapshots per project (`--keep` accepts 1–100). It removes starting
snapshots of finished sessions and older ending snapshots. Saved receipt JSON
and its recorded diffs stay unchanged. Future comparisons can become unavailable
if their matching old endpoint was removed. Freed SQLite pages are reused; the
file's physical size may stay unchanged. Receipts themselves eventually fill a
bounded store; preserve it and select a new `--store` when needed. Separate stores
do not share comparison history or private project identity.

Backups are consistent, exclusive 0600 SQLite copies, including active sessions.
They contain private project locators and local fingerprint keys: **keep them
private**, unlike aggregate share cards. An existing destination is refused.
To restore, create a new private directory (0700) and copy the backup there as
`sessions.sqlite3` (0600), then use that directory with `--store`. Check `history`
and `session active`; use `session recover <id>` for an unknown ending boundary.
Keep the original store until you have checked the restored copy.

After a process crash, `forkit-radar storage recover` lets SQLite replay a valid
rollback journal without creating a receipt. It does not repair corruption or
invent a session end time. A disk-full write can still fail; free disk space,
check `session active`, then stop or recover explicitly. Already oversized or
corrupt databases from older builds remain refused; retain their files and any
journal for diagnosis rather than deleting them. Maintenance is always local and
accepts the same `--store` and `--json` options as the session workflow.

## Local share cards

```console
forkit-radar card --output receipt.html
forkit-radar card --output receipt.svg
forkit-radar card --output receipt.json
forkit-radar card <session-id> --json
```

Omit the session ID for the latest receipt in the selected store. Open the HTML
locally to **Save PNG** (1200 × 630) or SVG. Everything, including the fonts and
PNG conversion, uses local browser facilities; no external assets, analytics,
API, network permission, account or publisher is required. PNG is produced by
the browser's [canvas `toBlob`](https://developer.mozilla.org/en-US/docs/Web/API/HTMLCanvasElement/toBlob),
so font rasterization can differ across operating systems. SVG/JSON generation
needs no browser. Existing output files are never overwritten (0600 on creation).

Cards use the separate strict
[`SessionCard 1.0` schema](src/forkit_radar/sessions/session-card-v1.schema.json).
The exporter directly projects an allowlist of aggregate fields; it never dumps
a private receipt and then redacts it. Allowed: the selected tool label, elapsed
whole minutes (under one minute shown explicitly), file counts, declaration-entry
counts by change/category, comparison availability, outcome and a fixed Passport
association state. No project/agent names, timestamps, file paths, dependency or
MCP/model names, session/project/Passport IDs, private fingerprints, keys, URLs,
arguments, source contents or chats cross that boundary. Private receipt/history
`--json` output is different and must not be used as a public card.

Partial counts stay lower bounds. Legacy metadata stays not captured; missing
comparison baselines stay unavailable. Recovery includes the interval until
recovery and has unknown duration. Dependency and lockfile declarations can
overlap: these are changed **entries**, not unique installed packages. Configured
tools/models are not proof of runtime use, and tool selection is not proof of
authorship. Core ID consistency is an explicitly declared association, not a
verified public Passport. Cards are unsigned local summaries. Review before
sharing; no publication occurs as part of export.

The product page is [`site/index.html`](site/index.html), preserving the supplied
cream/purple/teal theme and section structure. Its examples are illustrative, its
install instructions refer to this checkout/bundle, and it makes no signup,
live-network-count or public-release claim. No hosted site has been changed.

### Build an offline bundle for your current Python/platform

After the cumulative wheel validation below, supply that run's `dist` directory:

```console
python3 scripts/build_radar_bundle.py --project-wheels output/radar-foundation/run-EXAMPLE/dist --wheelhouse output/radar-wheelhouse --output output/forkit-session-receipt.zip
```

The archive includes Core/Radar wheels, hash-locked runtime wheels, the standalone
installer and licenses. Its manifest checks every wheel and the exact lock before
installation. Checksums establish bundle integrity, not publisher authenticity.
The current-platform bundle is not a universal binary or a substitute for release
validation. For offline **source** installation, first provision both the build
and runtime locks into a wheelhouse, then run
`python3 scripts/install_radar.py --offline --wheelhouse /absolute/wheelhouse`.
The builder/runtime use [pip hash checking](https://pip.pypa.io/en/stable/topics/secure-installs/)
and binary dependencies; application packages always come from the local build.

## Dependency, configuration and previous-session details

New sessions capture a small, fixed set of project metadata alongside the file
baseline. `receipt --json` and `history --json` return version **2.0** private
receipts. Existing 1.0 receipts and active sessions keep their original shape and
bytes; current writes migrate the session database to schema 2 without retroactive metadata capture. The original receipt formats are unchanged.
The updated reader accepts both versions. Older binaries cannot read 2.0 records.

### Supported metadata

| Source at the selected Git root | What is compared |
| --- | --- |
| `package.json` | Declared dependency constraints in dependencies, devDependencies, optionalDependencies and peerDependencies |
| `package-lock.json`, `npm-shrinkwrap.json` v2/v3 | Registry-style locked versions at stable package slots, including nested copies |
| `pyproject.toml` | Static PEP 621 project dependencies and optional-dependencies |
| `requirements.txt` | One PEP 508 requirement per line; ordinary comments allowed |
| `.codex/config.toml` | Project MCP names as local pseudonyms, transport/enabled declarations, model and model_provider references |
| `.cursor/mcp.json`, `.mcp.json` | Cursor and Claude Code project MCP names as local pseudonyms and transport declarations |
| `.claude/settings.json` | Project model reference |
| Explicit `--agent-manifest` | Existing Radar adapter's supported declared tool names/transports/permissions, model names/versions/providers/Passport references, and temperature/top_p/max_tokens |

These are **declarations**. Lockfile entries do not prove packages are installed;
MCP entries do not prove a server was approved, launched or used. Configured model
references do not prove an active model/runtime. No inference API, shell script,
MCP executable, endpoint, editor database, prompt, chat, credential file or model
weight is consulted. User/global settings, CLI/profile overrides and managed
settings remain outside this project-layer scope.

MCP server keys are HMAC pseudonyms scoped to the private store. A short fixed
list of familiar names, such as `playwright`, may appear as **MCP declarations**;
that name does not authenticate the executable. Other names remain unnamed. Raw
server names, commands, arguments, URLs, environment variables, headers and raw
config digests are not retained. Changes solely to those excluded command/URL/
argument/env fields are **not reported**. This is a scoped metadata comparison,
not a full config audit or secret scanner. Public sharing is a separate export.

Npm manifests and lockfiles are displayed as separate sources, so one package
update can produce two declaration changes. They are not summed into an installed
package count. If both npm lockfiles exist, both declarations are compared;
Forkit does not resolve npm's effective tree or precedence. Python uses the
maintained `packaging` parser. Names/extras/specifiers are normalized; environment
markers are compared through local pseudonyms, never evaluated or displayed.
Equivalent but differently written npm constraints can still be declaration
changes; Forkit does not run a dependency resolver.

The alpha deliberately abstains on direct URL/git/file/workspace/npm-alias specs,
arbitrary npm tags or Python arbitrary-equality specs, dynamic Python dependency
metadata, pip includes/options/continuations/hashes, monorepo workspace expansion,
legacy/new unsupported lock versions and formats such as pnpm, yarn, bun, uv,
Poetry, Cargo, Go, Gem and Composer. Recognized unsupported root files make
coverage partial. Only root manifests are parsed; nested manifests still fall
under file capture where eligible, without semantic dependency coverage.

Each dependency source is capped at 512 facts; total metadata at 1,024 facts and
180 KB. JSON npm inputs are at most 1 MiB; TOML, requirements and client/agent
metadata use the existing 64 KiB reader. Duplicate keys, changing files, unsafe
links, denied reads, invalid/unsupported entries and bounds remain visibly
incomplete. Known intersections can report changes; additions/removals require
complete before/after coverage for that source. Missing files are known absence;
unreadable files are not. Records remain bounded to 1 MiB (100,000 JSON nodes for
private session records; existing public input limits remain unchanged). Large
previous comparisons are omitted with an explicit size-limit reason to preserve
the current receipt; oversized metadata comparison details become unknown.

### Optional existing Passport

Select the agent being built explicitly. This does not attach a Passport to the
coding assistant or infer the agent's creator:

```console
forkit-radar session start --tool codex \
  --registry /absolute/existing/core-registry \
  --passport-id <existing-64-hex-agent-passport-id>

# Optional: also compare one selected Radar agent manifest.
forkit-radar session start --tool cursor \
  --agent-manifest /absolute/agent-manifest.json \
  --registry /absolute/existing/core-registry
```

The same options work with `session run` before `--`. Core's existing identity
algorithm and raw JSON checks run before association; no ID is generated or
repaired on this path. A conflicting manifest/selected ID or invalid Core
identity stays conflicted. Missing registry/model/manifest data stays visible.
An unchanged agent ID can coexist with a changed declared model reference.
Version/Passport transitions are shown as declared selections; they do not infer
Core lineage, accepted enrollment or cryptographic continuity. The Core registry
and its existing lineage remain untouched. Without an explicit Passport, the
rest of the receipt works normally. Creating a local Passport uses the existing
account-free `passport create` command below.

### Three different comparisons

- **During this session:** selected start → finish, as before. Existing dirty
  files/declarations form the baseline.
- **Since a comparable receipt:** previous finish → current finish. Prefer the
  newest completely captured endpoint in the same project and selected metadata
  context; if none exists, use the newest compatible partial endpoint with
  uncertainty. The search is bounded to 100 previous project sessions. Recovered
  sessions and legacy records without metadata do not qualify.
- **Between sessions:** that same baseline finish → current start. These changes
  are kept separate from changes during the active session.

The explicit agent-manifest and registry locations must match the baseline's
selection. Tool selections and selected Passport IDs may change; this records a
user-selected transition, without establishing agent lineage. A skipped newer
receipt count and the actual baseline ID are included. `previous_session_id`
remains the ordinary most recent history pointer; `since_previous.baseline_session_id`
is the comparison baseline. No baseline means unavailable comparison, not zero
changes. An unchanged comparable session produces zero changes.

“Change categories” is a deterministic count of the nonempty groups **files,
dependencies, configuration, tools, models and Passport selection**. It is not an
AI importance rating, risk score or count of independent actions. Coverage and
recovery qualifiers apply to every displayed comparison.

Format references: [npm package.json](https://docs.npmjs.com/cli/v11/configuring-npm/package-json/),
[npm lockfiles](https://docs.npmjs.com/cli/v11/configuring-npm/package-lock-json/),
[PyPA project metadata](https://packaging.python.org/en/latest/specifications/pyproject-toml/),
[PyPA requirement parsing](https://packaging.pypa.io/en/stable/requirements.html),
[Codex configuration](https://developers.openai.com/codex/config-reference/),
[Claude project MCP declarations](https://code.claude.com/docs/en/mcp),
and [Claude settings](https://code.claude.com/docs/en/settings).

## Existing discovery and Passport foundation

This development package supplies versioned document contracts, bounded passive
application/process discovery, passive MCP/model/agent metadata adapters, raw Core
Passport checks, and persistent unsigned enrollment proposals. Local session
revision/history and reconstruction are implemented separately. Accepted enrollment,
signed agent revision/identity history, runtime attachment and publishing remain
unimplemented.
The authoritative sequence and current checkpoint remain in
[`FORKIT_RADAR_LOCK.md`](../../FORKIT_RADAR_LOCK.md).

## Available commands

After the local wheel installation described below:

```console
forkit-radar --version
forkit-radar schema manifest
forkit-radar validate manifest selected-manifest.json
forkit-radar scan --no-save
forkit-radar scan --no-save --source applications
forkit-radar scan --no-save --source processes --json
forkit-radar scan --no-save --source mcp --project /absolute/selected/project
forkit-radar scan --no-save --source models --models-root /absolute/ollama/models
forkit-radar scan --no-save --source agents --project /absolute/langgraph/project
forkit-radar scan --no-save --source agents --agent-manifest /absolute/agent-manifest.json
forkit-radar scan --no-save --source agents --agent-manifest /absolute/agent-manifest.json --registry /absolute/core-registry
```
`scan --no-save` collects supported **product candidates**, never enrolled agents
or authenticated runtimes. This development command requires `--no-save` while
transactional storage and the complete default CLI remain later steps. It does
not compare baselines, infer removals, calculate coverage, enroll, accept a
revision, or persist a snapshot. The JSON option is a **private diagnostic**,
not the public aggregate export. Source slots and provisional component IDs are
random and scoped to this invocation; they must not be used as continuity IDs.
Installed bundles and process observations stay separate, including duplicates
of the same product. Candidate count is neither agent count nor a trust score.

Each source reports complete, missing, partial, denied, timeout, malformed or
unsupported. `complete` covers only that named metadata query; identity fields
remain partially measured. Missing means the selected metadata file was absent,
not that no installation exists elsewhere. Process visibility restrictions and
processes disappearing during inspection produce partial results. Exit 0 means
all selected queries were complete/missing; exit 1 means partial/unavailable
scope with usable diagnostics; exit 2 is invalid command/document input.

`validate` reads only the explicitly selected regular file, with a 1 MiB limit.
It rejects a final symlink, duplicate JSON keys, invalid Unicode, floats,
non-finite values, out-of-range integers, excessive depth, unknown fields and
contradictory contract fields. Errors do not echo document contents or paths.
It performs no discovery, network requests, key generation or registry writes.
Success means **structure valid**, never authentic, enrolled, signed or safe.

The Python boundary is `forkit_radar.contracts.read_contract(name, raw_bytes)`.
It returns immutable models with immutable nested sequences. Use this boundary
for untrusted input; do not bypass it with Pydantic `model_construct`, load
duplicate-prone JSON first, or treat a parsed authority/evidence record as a
trusted store entry. Labels inside supplied documents remain claims until the
appropriate verifier, expected authority and retained state substantiate them.

## Current detector scope

| Source | Read scope | Limitations |
| --- | --- | --- |
| macOS application metadata | Twelve exact `Info.plist` locations: system and user `Applications` folders for ChatGPT, Claude, Codex, Cursor, Windsurf and Ollama | Requires an allowlisted bundle ID/executable pair. Other install locations are outside scope |
| OS process executable metadata | Native executable paths, reduced immediately to the finite product catalog | Exact native basenames for `claude`, `codex`, `opencode`, `ollama`, plus known main app bundle executables. No generic Python/Node, package-runner, module, helper or descendant inference |
| Codex MCP | `$CODEX_HOME/config.toml` or `~/.codex/config.toml`; selected project's `.codex/config.toml` | Independent declaration layers; selecting a project does not establish Codex trust. CLI/profile, system, managed, ancestor and plugin layers are outside scope |
| Cursor MCP | `~/.cursor/mcp.json`; selected project's `.cursor/mcp.json` | Project entries shadow matching user entries only within the selected files. Incomplete layers leave precedence unresolved; approval/runtime activation is unknown |
| Ollama model metadata | `$OLLAMA_MODELS/manifests` or `~/.ollama/models/manifests`; explicit `--models-root` overrides | Four directory levels (registry/namespace/model/tag), Docker v2 manifest subset; model-layer digest and size are declarations. Aliases, blob bytes, template/license/config blob contents and API are not read/exported |
| LangGraph project | Explicit `--project` and its `langgraph.json` | Bounded Python graph references only. No import, graph factory call, dependency resolution, source or `.env` read. JavaScript/dynamic forms are unknown |
| Agent manifest | Explicit `--agent-manifest` using the existing Radar `manifest` contract | Passive agent scope only; selected fields remain unverified declarations. Claimed logical ID is discarded; each scan assigns a fresh provisional key |

The default scan uses the first five adapters. Project and agent-manifest inputs
enable their corresponding additional adapters; Radar never searches arbitrary
projects. Missing project selection is reported as unsupported, not an empty
project. `--source agents` requires a selected project or agent manifest.

MCP server names, commands, arguments, URLs, headers, environment values, graph
names/entrypoints and model aliases do not cross automatic ingestion. Raw keys
exist transiently inside the Cursor worker only to compare the two layers;
they are neither retained nor hashed. MCP entries are **server declarations**,
not an inventory of actual callable tools. Tools, model references and settings
that cannot be observed remain null/unsupported, never invented or known-empty.
All automatic metadata identities remain unknown.

Explicit agent manifests may intentionally contain private identity/tool/model
metadata. `--json` includes those selected fields, so it remains a private
diagnostic; plain output uses fixed labels. All supplied evidence origins are
downgraded to `declared`. A supplied Passport ID is only an association claim.
Explicit `--registry` selection adds raw Core consistency checks; it does not
authenticate the association. Signature validation and runtime binding remain later steps.
Copied manifests cannot create a shared logical identity.

Adapter details (entry ordinal, transport, configured activation, selected-file
precedence and declared size) are ephemeral diagnostic fields outside the
versioned Manifest. They are not yet revision inputs. Entry order, duplicate
names, paths, digests and similarity must never become continuity keys. Pending
enrollment now records an explicit private source selection separately; S06 must
define any additional comparable dimensions before claiming detection of changes
to these details. Declared artifact completeness covers descriptors, not bytes.

These formats follow the [Codex MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli)
and [configuration precedence](https://learn.chatgpt.com/docs/config-file/config-basic),
[Cursor's MCP documentation](https://prod.cursor.com/help/customization/mcp),
the [LangGraph CLI configuration](https://docs.langchain.com/langsmith/cli), and
[Ollama's manifest implementation](https://github.com/ollama/ollama/blob/main/manifest/manifest.go).
The tests include metadata fetched on 14 September 2026 from
[Ollama's public llama3.2 manifest](https://registry.ollama.ai/v2/library/llama3.2/manifests/latest)
and a test-owned LangChain/LangGraph agent that completes a tool loop using a
deterministic model double. This proves that concrete framework path locally;
it does not establish production LLM behavior, live MCP protocol compatibility,
or the authenticity of a discovered agent. The scanner never executes that fixture.

New metadata files are limited to 64 KiB, 32 selected entries per source, 32
JSON/TOML nesting levels and 20,000 parsed nodes. Ollama visits at most 256
directory entries, reads only depth-four manifests and retains at most 32 models.
Unknown, invalid and unprocessed entries are counted separately; partial results
must not drive removals. The shared directory-handle and worker limits below
also apply. Python 3.11+ uses `tomllib`; Python 3.10 uses hash-pinned `tomli`.

The installed `ChatGPT.app` / `com.openai.codex` / `ChatGPT` variant was observed
and validated on macOS 26.6.2 arm64. Process-only metadata at that executable
cannot distinguish ChatGPT from Codex and stays explicitly ambiguous. Other
catalog entries have synthetic format/signature conformance tests; broad product
version support and independent field accuracy are unmeasured. macOS is the
real local validation environment. Linux process code and the configured Ubuntu
CI jobs do not establish an Ubuntu support claim until actually run; the macOS
application adapter reports unsupported there. Windows is unsupported.

The scanner reads no process command lines or environments. Pinned psutil 7.2.2
has a command-line fallback inside its public `exe()` API; Radar overrides that
fallback before collection and tests the native API boundary for empty/denied
executable results. See [the pinned upstream implementation](https://github.com/giampaolo/psutil/blob/release-7.2.2/psutil/__init__.py)
and [psutil API documentation](https://psutil.readthedocs.io/en/release-7.2.2/).
Only allowlisted product labels and a narrow numeric version format survive
ingestion. Plist keys outside the three selected bundle fields are discarded;
arbitrary metadata, executable paths, PIDs, commands, environment values and
exception text never enter results. No endpoint, DNS, HTTP, MCP-command execution,
source-code read, model-weight read or background installation occurs.

Each collector uses a fixed, installed Radar-owned Python worker. These workers
make timeouts enforceable; they never invoke discovered executables. Each gets
a 3-second supervisor deadline with bounded termination/reaping. Cooperative
collection has a 2-second budget; process work stops at 4,096 entries or 128
candidates. Each plist is at most 64 KiB, with at most 16 path/nesting levels and
2,048 parsed nodes; worker stdout is capped at 256 KiB and stderr discarded.
Files are opened through directory handles, rejecting symlink components, hard
links, special files, duplicate plist keys and detected replacement/change.
This is error containment, not a sandbox for arbitrary plugins or a guarantee
against kernel stalls. A concurrently renamed ancestor can still make metadata
historical: no code-integrity or stable path-binding claim follows from this scan.
Future change comparison must preserve the last comparable successful source
baseline when these results are partial; no such comparison is implemented yet.

Product catalog concepts were adapted from the public MIT-licensed AI Footprints
reference at `ec7250cf39a185a5817835c50853862e68053318`. Its command parsing,
loopback probes, confidence labels and product-derived identity hashes were not
ported. The distributed `forkit_radar/THIRD_PARTY_NOTICES` preserves its license.

## Core association and pending enrollment

```console
forkit-radar passport inspect --file /absolute/passport.json
forkit-radar passport inspect --passport-id FULL_CORE_ID --kind agent --registry /absolute/core-registry
forkit-radar passport create --input /absolute/model-request.json
forkit-radar passport create --input /absolute/model-request.json --output /absolute/new-model.json
forkit-radar passport create --input /absolute/agent-request.json --model-passport /absolute/new-model.json --output /absolute/new-agent.json
forkit-radar enroll --agent-manifest /absolute/agent-manifest.json --registry /absolute/core-registry
forkit-radar enroll --agent-manifest /absolute/agent-manifest.json --store /absolute/private-store --save-pending
forkit-radar enroll --project /absolute/langgraph-project --graph-key calculator --store /absolute/private-store --save-pending
forkit-radar enrollment list --store /absolute/private-store
forkit-radar enrollment inspect PROPOSAL_UUID --store /absolute/private-store
forkit-radar enrollment cancel PROPOSAL_UUID --store /absolute/private-store
```

Creation input contains required, explicitly provided Core metadata only:

```json
{
  "passport_type": "model",
  "name": "example-model",
  "version": "1.0.0",
  "creator": {"name": "Explicit operator declaration", "organization": null},
  "task_type": "text-generation",
  "architecture": "transformer"
}
```

An agent request additionally requires its real `model_id` and Core agent enum
values, for example `customer-support` / `ReAct`. `--model-passport` must contain
a raw-valid ModelPassport matching that ID. Names, versions, creator and model
details are never guessed. Preview writes nothing; `--output` explicitly creates
a mode-0600 Core document, refuses existing destinations, and preserves Core's
serialization/ID algorithm. It does not register or overwrite entries in an
existing Core registry. Optional artifact/prompt/configuration creation fields
are outside this initial command's scope.

Radar validates bounded original JSON, required raw types, the stored ID through
Core's `verify_passport_id`, expected record location/type and the Core schema
before using a Passport. It never uses loader-repaired missing IDs as evidence.
Core's valid finite float settings are accepted through a separate Core parser;
Radar's integer-only JCS contract is unchanged. Arbitrary Core metadata and
configuration are neither retained nor hashed into an association. Returned
private diagnostics include only selected identity fields, IDs, reason and time.
`consistent` means identity/schema consistency; it does not establish authorship,
ownership, live software, artifact integrity or current lifecycle acceptance.

Lookup reads only the requested `agents/ID.json` or `models/ID.json`; it does not
initialize, index, repair or mutate Core's registry. Association uses explicit
references only. A different selected ID conflicts with an existing declaration;
multiple candidate IDs stay ambiguous. Declared identity mismatches and invalid
model references stay conflicted. No name, path, artifact or model similarity
search establishes a connection. Missing or unreadable model references remain
visible even when the agent Passport's own ID is consistent.

`enroll` previews one selected agent manifest or exact LangGraph graph key.
`--passport-id` can supply an explicit candidate; repeated IDs expose ambiguity.
`--save-pending` reserves a fresh random logical-agent ID and source slot in a
private SQLite proposal. These are **pending reservations**, not enrolled agents.
The manifest still has no logical identity. Missing metadata, Passport/model
checks, revision preparation and signing authority remain explicit blockers.
Ambiguous/conflicted associations cannot be saved until resolved. Selecting a
source again checks its allowed metadata before saving; later acceptance must
recheck the source, Passport and authority. No signature or accepted binding is
fabricated. S06 prepares revisions; S07/S08 supply authority and signed acceptance.

The default store is `~/.forkit-radar/enrollment.sqlite3`; `--store` selects a
different private directory whose parent must already exist. New directories
and files use 0700/0600. Existing permissive modes, symlinks, hard links, unknown
schema versions or unexpected SQL schema are rejected. Private locator JSON is
stored in a separate table, never in proposal/manifest output. A per-store random
HMAC key makes locator tokens local; it is **not a signing authority**, recovery
credential or hardware-backed key. Losing/copying this store cannot prove continuity.

Repeated pending selection of the same source is rejected. Cloned files and
separate selected graphs reserve distinct logical IDs. Cancellation preserves
the original canonical draft and appends a cancellation record; selecting it
again reserves a new ID. Read-only inspection does not create a store. Plain
output uses fixed labels and opaque IDs; `--json` is private diagnostic metadata,
not the aggregate public export.

SQLite uses explicit version-1 initialization, validated schema, foreign keys,
FULL synchronization, DELETE journals and serialized transactions. Process-local
connections are serialized; `BEGIN IMMEDIATE` controls other writers. Lock waits
and SQL work have bounds. Radar avoids extra open/close handles on a live database,
following [SQLite's Unix locking guidance](https://www.sqlite.org/howtocorrupt.html#posix_advisory_locks_canceled_by_a_separate_thread_doing_close_)
and disables trusted schema per [SQLite's guidance](https://www.sqlite.org/pragma.html#pragma_trusted_schema).
Never delete recovery journals or copy a live DB as a backup. This foundation is
for local filesystems; full migration, backup, history and rollback detection
remain S11. Permissions and SQLite do not protect against a compromised user/OS.

## Contracts

| Contract | Purpose |
| --- | --- |
| `manifest` | Scoped identity, tools, model references, artifact metadata and settings |
| `observation` | Source slot, detector, time and completeness, outside the content digest |
| `evidence-state`, `evidence` | Separate evidence axes, reasons, scope, support references and expiry |
| `authority`, `trust-policy`, `source-binding` | Public authority metadata, locked trust rules and private binding references |
| `transition` | Explicit pending proposals; parsing never approves an action |
| `runtime-challenge` | Nonce, audience, revision, instance, source slot and collector peer context |
| `binding-predicate`, `binding-statement`, `dsse-envelope` | Receipt shapes; signature and chain verification are later work |
| `public-snapshot` | A separate allowlist of bounded aggregate counts and random publication IDs |

Schema version `1.0` uses lowercase UUIDv4-shaped opaque local identifiers and
64-character lowercase hex digests. Shape validation cannot establish that an
ID was randomly generated, that a source is genuine, or that a nonce is fresh.
It cannot distinguish a fabricated evidence record from a collector's record.
Trusted storage and actual verification are necessary before using any stronger
label. The DSSE fixture intentionally contains a fake signature to make this
boundary explicit.

All nullable wire fields are required: missing is not silently repaired. A
known-empty collection is `[]`; unavailable data is `null` with its completeness
status. `ObservedText`/`ObservedDigest` distinguish unknown from known absence
through `origin`. Unknown values must be null. Collections have at most 256
members; semantic set keys must be unique. Parsing preserves order; S06 will
normalize semantic sets before revision hashing. Decimal settings are strings
with at most eight fractional digits; no prompt or credential fields exist.

Published JSON schemas use Pydantic's JSON Schema 2020-12 shape vocabulary.
Cross-field conditions, bounded raw JSON parsing and all trust decisions are
not completely expressible in these generated files. Use `read_contract` for
complete structural checks. Never use JSON-schema success as authorization.

## Reproducible local development

Run these from the repository root with Python 3.10 or newer. Python 3.11 is the
local baseline. Core and Radar are built from this checkout because public PyPI
publication has not been established; `uvx forkit-radar` is not a release claim.

```sh
python3.11 -m venv .radar-venv
.radar-venv/bin/python -m pip install --require-hashes -r requirements/radar-dev.lock
.radar-venv/bin/python -m pip download --only-binary=:all: --require-hashes -r requirements/radar-runtime.lock --dest output/radar-wheelhouse
.radar-venv/bin/python scripts/check_radar_foundation.py --wheelhouse output/radar-wheelhouse
```

The check script builds Core and Radar wheels and source distributions, installs
the wheels into the development environment without resolving from PyPI, runs
the unchanged Core suite and Radar suite, checks distributed schema drift,
then installs only runtime dependencies and the locally built wheels in a fresh
environment using `--no-index` and hashes. It verifies imports and the CLI from
outside the source tree. The fresh install does not include test/framework
extras. It also runs controlled real native-process tests and installed passive
scans, retaining aggregate timing, source-status and Python audit/native-API
checks. These are not a full OS packet trace or representative accuracy study.
Downloading dependencies is a separate setup operation; the check
script does not contact a package index. Its local HTTP test fixtures may need
loopback socket permission in sandboxed environments.

Exact dependency versions and distribution hashes are in
`requirements/radar-{runtime,dev}.lock`. Those files lock dependencies; they are
not competing project plans. The `.in` files are reviewed resolution inputs.
To update intentionally, use the generation commands in the lock headers,
review the dependency changes and rerun the checks. Do not silently refresh a
verifier dependency or change policy versions.

Maintained libraries: [Pydantic](https://docs.pydantic.dev/latest/concepts/strict_mode/)
for strict typed validation, [rfc8785](https://github.com/trailofbits/rfc8785.py)
for JCS, and [PyCA cryptography](https://cryptography.io/en/latest/hazmat/primitives/asymmetric/ed25519/)
for Ed25519. Tests use published RFC known-answer vectors plus negative cases.
Passing primitive vectors does not establish DSSE verification, provenance
verification, key protection or production security. The existing Core identity
algorithm and serialization remain unchanged.
