# Optional Radar aggregate collector

This document describes the preserved manual schema-v1 `metrics` protocol. For
the new explicit-consent automatic `usage-v2` protocol and deployment controls,
read [USAGE_OPERATOR.md](USAGE_OPERATOR.md). The protocols have separate consent,
profiles, tables and public totals. Neither is enabled by default.


This is the Prompt 11 route module for the existing **Express/PostgreSQL** hosted
architecture. It is separate from Core identity, local Passport creation, Connect,
AI Footprints, account/auth flows and customer data tables. No hosted source or
production database has been changed. The Python CLI remains account-free and
offline by default.

The module is original OSS implementation. No private Registry or Connect source
was copied. It accepts the existing PostgreSQL pool and mounts as Express middleware,
so it does not need another account system or identity authority. Express 4.22.1 is
a development-only compatibility test dependency; pg 8.20.0 is the collector runtime
dependency. The CLI's Python dependencies are unchanged.

## Integrate with an existing hosted registry

Use a reviewed, isolated database migration and the existing HTTPS service:

```javascript
import {createHandler} from './collector.mjs';

// Mount before express.json() or any other body parser.
// Keep existing account, Passport and AI Footprints routes unchanged.
app.use('/api/v1/radar', createHandler({
  pool: existingPostgresPool,
  secret: reportingSecretBytes, // private 32-byte Buffer, supplied by operator
  enabled: false,               // explicit operator enable after validation
  environment: 'production',
  tlsTerminated: true,          // only behind the configured trusted HTTPS ingress
  // remoteAddress: req => req.ip, // only with an exact, reviewed trust-proxy policy
}));
```

Apply `schema.sql` explicitly to the selected database. Its tables are confined to
`radar_metrics`. Do not run migrations automatically when a user's CLI starts.
Use the existing platform's service identity, private database connection, TLS,
secret storage, request limits, logging exclusions and EU hosting policy. This
module is not deployment authorization, a verified public Passport service, an
authentication replacement, or permission to touch existing customer tables.

The exact raw request bytes must reach the handler. It refuses requests when a
prior JSON parser has consumed them. Production writes require an encrypted socket
or the explicit operator-configured TLS termination flag. A request header cannot
turn HTTPS enforcement off. HTTP loopback is available only in validation mode
with a separate explicit flag. The standalone runner binds 127.0.0.1.

The Radar page at `../site/` reads only the same-origin
`/api/v1/radar/metrics` route, without cookies, referrer, visitor telemetry or
third-party analytics. Its missing-collector state displays no invented numbers.
Deploying or mounting this page in the actual customer website remains a separate
reviewed publication operation.

## Protocol and exact consent

- `PUT /api/v1/radar/surfaces/<random UUIDv4>`: one latest aggregate snapshot.
- `DELETE /api/v1/radar/surfaces/<random UUIDv4>`: authenticated withdrawal.
- `GET /api/v1/radar/metrics`: current sanitized combined counts.

Each client profile generates an independent 256-bit reporting credential and
random public surface ID. Neither derives from hardware, username, path, Core
Passport ID or a signing authority. The credential authenticates reporting updates
only; it is not proof of a real install, unique person or AI execution.

PUT uses `Authorization: Bearer <reporting credential>`, exact
`Content-Type: application/json`, Content-Length and canonical JSON up to 32 KiB.
No redirects, compression, transfer encoding, browser-origin writes or unexpected
fields are accepted. The Python client requires the saved preview's SHA-256 before
sending. The ACK echoes both accepted sequence and exact payload SHA-256.

The wire shape is implemented independently in `contract.mjs` and the Python
`forkit_radar.reporting.contracts.Contribution`. It allows fixed keys/enums,
bounded safe integers, calendar dates, four UTC calendar weeks and nullable
discovery counts. These ASCII-only values serialize identically with RFC 8785.
Canonical byte comparison rejects duplicate keys and alternate representations.

Updates authenticate the credential, lock the selected surface transactionally,
and replace its snapshot. Identical sequence/body retries return unchanged and do
not refresh the report's age. Older sequences and same-sequence changed bodies are
rejected. Concurrent registration obeys the database-wide profile capacity.
Withdrawal creates a revocation record even when it races ahead of a first upload,
preventing a delayed submission from recreating a withdrawn contribution.

The client records consent/credentials and local operation counts in a separate
private `reporting.sqlite3` beside its selected session store, using existing
hardened SQLite mechanics and 0700/0600 permissions. It reads original receipts and
their retained evolution evidence; it does not rebuild Core, modify receipt bytes,
create Passports, or read project source during preview.

Reporting is disabled by default and never sends automatically. Enable records
future local scan/Passport-create operations. Each preview explicitly includes
retained receipts from the current UTC week plus three previous weeks, including
pre-consent receipts. Disabling stops journal collection and sending, while an
already published snapshot remains until withdrawal or expiry. Existing private
session history remains available throughout.

## Counting definitions

| Metric | Definition and practical limit |
| --- | --- |
| Reporting profiles | Latest non-withdrawn profiles received within 7 days, with a report generated no more than 7 calendar days ago. This is an opt-in installation-profile proxy, not all installs or unique people. |
| Successful scans | Recorded Radar CLI attempts whose selected sources all completed or were absent. No historical/private/unrecorded scans are estimated. |
| Weekly Active Passports | Distinct consistent selected Agent Passport IDs in retained receipts during the current UTC week, deduplicated locally within a profile, then summed. Cross-profile duplicates remain possible; raw IDs never leave the device. |
| Repeat-check rate | Profiles with receipts/scans on at least 2 distinct UTC dates this week / profiles with either activity on at least 1 date. Passport creation alone does not count as a repeat check. |
| Session Receipts | Retained receipts in the current UTC week and 3 previous weeks, summed across the latest eligible profiles. |
| Meaningful changes | Prompt 10's documented grouping policy, including observed gaps between adjacent comparable sessions. Unknown edits cannot be counted. |
| Reconstructable-change rate | Known events with checked local Passport + session + before/after revision evidence / all recorded meaningful events. Includes unattributed between-session changes in the denominator. Any incomplete original count evidence makes the combined percentage null. This is not a trust or safety score. |
| Passport versions created | First successful Radar CLI output of each distinct Core ID recorded in that profile while enabled. Repeated output of that ID does not count again. It is not a globally verified mint count or logical-agent lineage. |
| Model/agent observations | Each current profile's latest recorded scan from the last 7 UTC dates. Only selected, complete/absent categories contribute; failed/unselected categories are null. Category-specific contributing-profile counts are exposed. Sources and profiles can overlap. |
| Total installs | Always unknown/null. Private offline use and people who decline reporting cannot be measured by this service. |

Rates are integer **basis points**, with 10000 meaning 100%. A zero denominator
is null, not 0% or 100%. Counters can decrease after corrections, withdrawal,
expiry or window rollover. They are current reported activity, not permanent
lifetime totals. There is no claim of globally distinct installed models/agents.

At least five current profiles are required before aggregate counts are exposed.
An empty collector can state that it has no current reports. Small nonempty cohorts
return `collecting` with no counts. This reduces direct single-report exposure; it
is not anonymity, differential privacy or resistance to differencing attacks.
Validation-mode responses are visibly labelled as validation fixtures by the page.

## Retention, abuse controls and operator responsibilities

The application stores HMAC-derived public-surface handles, hashed reporting
credentials, the latest count payload, its sequence/digest, receive time and
withdrawal state. It stores no raw surface ID, raw credential, IP address, private
Passport ID, source hashes, source text, project names, paths, model names, prompts,
chats or user account data. Requests necessarily expose connection metadata and
the newly generated reporting credential to the chosen collector during transport.

The module does not log requests or exception contents. Existing ingress,
observability and access logs must separately exclude Authorization, bodies,
surface URLs and raw IPs for these routes. Configure retention/access controls for
any infrastructure metadata and document them before collecting public data.
No application-level policy can certify a hosting provider's actual log settings.

Stale profiles leave public totals after seven days. GET maintenance nulls old
contribution bodies older than 31 days; an idle service needs an operator-scheduled
equivalent maintenance query for a strict elapsed-time retention guarantee.
Withdrawal nulls the body/digest immediately. Minimal HMAC handle, credential hash,
sequence and withdrawal metadata are retained to reject replays; no automatic
tombstone expiry is promised. Database backups, WAL and infrastructure logs follow
the operator's explicit retention policy; previously copied public counts cannot
be recalled. There is no stored series of old contribution bodies.

Shared PostgreSQL counters enforce per-address and global hourly request limits
(default 120/address and 5000/global). HMAC rate keys expire through request-time
maintenance after roughly two hours. Forwarded headers are ignored by default.
For a reverse proxy, inject an address resolver only after configuring the exact
trusted proxy topology; otherwise all requests may share the proxy's limit.
The standard profile cap is 10000, including revocation metadata. SQL statements,
locks, bodies, headers and request time are bounded. Upstream request/connection
limits remain necessary. Counter authentication and rate controls do not prevent
a determined actor from creating multiple pseudonymous profiles; self-reports
are not verified adoption.

Preserve the reporting secret securely. Rotating it without a reviewed migration
would orphan existing handle/credential lookups; no transparent rotation is
implemented. The secret is a service pseudonymization/authentication key, separate
from Core and future enrolled-agent signing. Do not silently reset a live database
or key to bypass revocations, limits or failed checks.

## Reproduce local checks

From this directory:

```console
npm ci --ignore-scripts
RADAR_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/forkit_p11_validation npm test
RADAR_TEST_DATABASE_URL=postgresql://postgres@127.0.0.1:55432/forkit_p11_validation node tests/workflow.mjs --keep-open
```

Tests require a **disposable** database named `forkit_p11_*`; they refuse other
database names and truncate only their own metrics tables. The shown no-password
connection is for the task's isolated loopback fixture database only, not a hosted
configuration. The installed Python CLI/Core wheels must be present in
`core/.radar-venv` (override `RADAR_TEST_PYTHON` if needed).

The workflow performs actual Python CLI preview/send/retry/disable/withdraw calls
against Node HTTP and PostgreSQL, then serves the existing Radar site with clearly
labelled fixture metrics for browser checks. It makes no AI inference call and
produces no user-adoption evidence.

The standalone operator runner accepts `RADAR_METRICS_DATABASE_URL`,
`RADAR_METRICS_SECRET` (32 bytes as hex), `RADAR_METRICS_ENABLED=1`,
`RADAR_METRICS_ENVIRONMENT=production`, `RADAR_METRICS_TLS_TERMINATED=1` when
appropriate, and an optional local port. Use `node server.mjs --migrate` only for
an explicitly selected migration, then `node server.mjs` to run. Provision
credentials through the host's private secret mechanism, never committed files.

References: [node-postgres transactions](https://node-postgres.com/features/transactions),
[Express proxy trust](https://expressjs.com/en/guide/behind-proxies/),
[PostgreSQL INSERT/ON CONFLICT](https://www.postgresql.org/docs/current/sql-insert.html).

