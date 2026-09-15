# Optional usage counts — usage-v2

Local Forkit needs no signup, login or reporting. Install, create local Passports,
capture sessions, view history/diffs/summaries and generate local cards with
reporting disabled. No public collector is included or enabled by this candidate.

After your first useful original receipt, inspect the policy:

```console
forkit-radar usage policy
forkit-radar usage status
```

If you choose a collector whose operator has published its privacy and retention
notice, explicitly enable new automatic-count consent:

```console
forkit-radar usage enable --endpoint https://YOUR-COLLECTOR/api/v1/radar --consent usage-v2
```

Replace the example hostname with that operator's actual endpoint; it is not a
Forkit service address. If your first receipt is in a custom store, pass the same
`--store PATH`. The command itself sends nothing. Add `--include-latest` only if
you choose to include the most recent existing receipt. Otherwise only future
original operations count. Earlier Footprints/manual consent never upgrades.

```console
forkit-radar usage preview
forkit-radar usage disable
forkit-radar usage withdraw
```

Preview shows the current snapshot without sending. It can change with later
activity; this is automatic reporting after consent, unlike the older exact-file
`metrics preview/send` feature. Disable cancels queued snapshots and prevents a
new attempt after disable completes. An already in-flight request may finish.
Withdrawal immediately disables future reporting locally, then removes the live
contribution when the collector confirms. An interrupted withdrawal stays disabled;
retry `usage withdraw`. Screenshots and previously published aggregates cannot be
recalled. Local receipts are never deleted by these commands.

During ordinary scans, Passport creation or receipt completion, a short-lived
worker may send at most once every 24 hours. Each attempt has a seven-second total
process deadline, including DNS. A lost acknowledgement retries the same snapshot
on a later ordinary use, up to three attempts; then a new cumulative snapshot
supersedes it. No daemon, timer service, login hook or startup task is installed.
Offline use always works. No later activity means no new send, and counts can lag.

One random installation reporting profile is shared across selected project stores
in `~/.forkit-radar/usage.sqlite3`. A private local override `FORKIT_USAGE_STORE`
supports isolated installations/tests. The reporting ID is separate from Passport
identity, and requests use a newly generated reporting credential. Incoming data is
pseudonymous, not fully anonymous: the collector necessarily sees connection
metadata. The wire payload contains coarse UTC dates, fixed labels (`codex`,
`claude-code`, `cursor`, `other`) and counts. It excludes prompts, code, chats,
filenames, paths, project/repository names, Passport/session IDs, source hashes,
existing credentials, hardware identifiers and arbitrary names. Private local
HMAC keys deduplicate original operations and Passports; those keys never leave.

Public metrics use the previous **7 or 28 complete UTC days**, excluding today.
The snapshot includes today's row so it can become eligible tomorrow. Profiles
count accepted opt-in installations, not total installs, users or hardware.
Resets, copied profiles, multiple devices and forged clients affect that estimate.
Downloads, old Footprints observations, CI and explicit validation profiles are
not community adoption. Use `--validation --allow-local-collector` with a loopback
collector for controlled tests; production intake rejects validation reports.
Never enable community reporting for examples, fixtures or internal testing.

- Original receipt creation counts once; viewing/exporting a receipt does not.
- Completed scan results and fully successful scans are separate. Detection
  observations can repeat across scans; they are not unique agents/models.
- Tool presence counts once per profile/tool/window and comes only from supported
  application/process discovery. A session's selected tool is a separate declaration;
  it does not authenticate who changed a file.
- Weekly activity requires a successful scan or original receipt. Repeat-check rate
  is profiles active on at least two UTC dates divided by profiles active on at least
  one date in the same seven days. It is not cohort retention.
- Weekly Active Passports sum locally distinct consistent Passport associations per
  profile. The same Passport on two devices can count twice. Missing current coverage
  stays unknown; no IDs are uploaded to deduplicate globally.
- Meaningful/reconstructable counts reuse the existing local evolution policy.
  Reconstruction links an observed change to a Passport, session and previous version;
  it is not authenticated AI execution. Incomplete history makes the rate unavailable.

Counts can decrease through corrections, expiry or withdrawal. Public cohorts and
positive tool/counter subgroups need at least five profiles. Smaller or unknown
values are suppressed. No extrapolation, global market estimate or paid-demand
claim follows from these counters.

The local journal keeps up to 10,000 count events and prunes events older than
35 days on the next capture; inactive local files are not pruned by a timer. A bounded local
Passport dedup set persists while that profile exists. Hitting a bound marks
collection incomplete and withholds rates. The reference collector physically
marks inactive bodies eligible for deletion after 35 days. Daily cleanup removes
them within 36 days when operated as required. Minimal authentication,
sequence and withdrawal metadata remain to reject replays (10,000-profile capacity;
no silent tombstone eviction). Rate-limit hashes expire after two hours. Production
operators must suppress request identifiers/credentials/IPs in application and
ingress logs, publish any residual retention, and limit backups to 35 days. Deleted
contributions may consequently remain in backups for up to 35 additional days;
restore must reapply withdrawals and expiry before reopening intake.
