# Optional counts — explicit consent, after your first receipt

All local features work without signup or reporting. There is no deployed collector
or preselected endpoint in this candidate. Normal reporting stays off.

After your first real receipt, read `forkit-radar usage policy` and the chosen
operator’s privacy/retention notice. If you want to contribute:

```console
forkit-radar usage enable --endpoint https://YOUR-COLLECTOR/api/v1/radar --consent usage-v3
forkit-radar usage preview
forkit-radar usage status
```

The hostname is a placeholder, not a Forkit service address. Native Mac users can
choose **Optional usage counts…** in the application menu and explicitly enter the
operator’s HTTPS endpoint. There is no consent prompt before the first receipt.
Saving consent sends nothing. It never imports old activity; the CLI’s optional
`--include-latest` explicitly includes only the most recent original receipt.
Pass `--store PATH` when that first receipt is in a custom store.

During later ordinary use a short-lived worker may send at most once every 24
hours. Each attempt has a seven-second process deadline; a lost acknowledgement
retries the same snapshot up to three times on later use. No daemon, scheduled
reminder, login task or reporting service is installed. Offline use works; without
later activity the website receives no update. Public numbers can lag.

## What the counts mean

| Count | Definition and limit |
| --- | --- |
| Participating profiles | Accepted opt-in installation profiles, not total installs or unique people. |
| Original receipts | Saved original session receipts. Reopening/exporting does not create another receipt. |
| Scans / successful scans | Completed scans / scans whose supported sources were all complete or missing. |
| Detection observations | Discovery observations, possibly repeated. Never unique agents or models. |
| Detected tool profiles | Fixed tool presence labels from supported application/process discovery. Separate from a session’s selected or hook-reported tool. |
| Meaningful changes | Supported recorded during-session file/metadata changes. Between-session changes are separate. |
| Active Passports | Distinct locally associated, internally consistent Passports in an active reporting profile/window. Not website registrations or verified owners. |
| View-days (v3) | A day with an intentional receipt/summary/history view. Native opening with receipts and deliberate tab clicks count; automatic refreshes do not. CLI views count only in an interactive terminal. |
| History view-days (v3) | A viewed day that included intentional history inspection. It is a subset of view-days. |
| Card exports (v3) | Successful local card saves through the CLI or native viewer. Repeated exports can count; they are not unique cards, public shares or referrals. |
| Repeat viewing (v3) | Profiles viewed on two or more complete UTC dates within the last seven, divided by profiles viewed in that window. Available after a second day; not a next-day cohort retention measure. |

Opening the portable offline HTML file, using PNG/SVG buttons in that file, or
looking at a screenshot is not measured. Local UTC view flags are deduplicated to
one per date; no exact click timestamps or selected receipt IDs are reported.

Public yesterday counters include only snapshots generated today, with the fresh
coverage-profile count shown beside them. Other totals use the last 7 or 28
complete UTC days. Minimum five profiles applies to cohorts and positive
subgroups. Unknown/suppressed values remain **—**. Incomplete collection suppresses
rates that would otherwise imply complete evidence. Repeat-check activity can be
background capture; repeat-viewing is the stronger, separate usage signal.

Local reconstructable-change rate checks retained Passport/session/previous-version
links. It is unsigned local history, not proof of AI authorship, factual truth or
authenticated identity continuity. It is not a website Passport registration count.

## Privacy and control

One random installation reporting profile is shared across local project stores.
Incoming data is **pseudonymous**, not fully anonymous: a random reporting handle
links snapshots and the service sees connection metadata. The payload has only
coarse UTC dates, counts and fixed `codex`, `claude-code`, `cursor`, `other` labels.
No prompts, chats, source code, paths, filenames, project names, Passport/session
IDs, source hashes, hardware IDs, existing secrets or credentials are uploaded.
A separate generated reporting credential authorizes updates/withdrawal; it does
not authenticate a person. Private deduplication keys stay on the device.

```console
forkit-radar usage disable
forkit-radar usage withdraw
```

Disable stops future attempts and cancels pending snapshots. A request already in
flight may finish. Withdrawal also removes the live contribution when the collector
confirms; retry an interrupted withdrawal. Neither recalls previously published
aggregates or screenshots. Local history is never removed.

Existing **usage-v2** consent retains its old strict payload and no view/export
counters. Withdraw that profile before choosing v3. Earlier Footprints/manual
consent never upgrades. Fresh consent does not backfill history.

Only real, externally used profiles belong in community counts. Use a separate
`FORKIT_USAGE_STORE` and `--validation --allow-local-collector` with loopback for
controlled tests; production rejects validation audiences. Do not enable community
reporting for examples, CI or internal testing. Downloads, automated scans, local
tests and registered accounts alone do not establish market demand. Resets,
multiple devices, copied profiles and forged clients limit all self-reported counts.
