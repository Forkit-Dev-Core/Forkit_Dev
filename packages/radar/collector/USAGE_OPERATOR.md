# Session Receipt count collector — release and operations

Candidate 0.1.0b5 is a local beta candidate, not deployed. The local OSS product works
without this service. Production collection requires a separate reviewed release.
The older manual `/metrics` protocol remains documented in README.md.

## Protocol and deployment

`PUT /api/v1/radar/installations/<UUIDv4>` replaces one opted-in installation
profile's snapshot; authenticated `DELETE` withdraws it. `GET /api/v1/radar/usage`
returns only sanitized aggregates. Hosted `GET /api/v1/radar/health` checks schema
access; the standalone runner exposes this check at `GET /health`.
Intake accepts strict schema 2.0/policy usage-v2 and schema 3.0/policy usage-v3. Acknowledgements echo the accepted schema version. Older consent/wire keys are unchanged. Public schema 2.0 retains existing keys and adds explicitly named daily and engagement fields. Validation audiences are refused by a
production collector. Generated credentials authenticate updates, not real users.

The client sends 29 daily count rows and local distinct-Passport windows. Public
totals use 7 or 28 complete UTC days, excluding today. Yesterday counters include only profiles with a snapshot generated today; publish daily_coverage_profiles beside them. A missing fresh cohort is unknown, not zero. The rolling seven-day repeat-view metric can appear after a second viewed date; it is not cohort retention. No raw Passport or session
ID leaves the device. Read the complete [count definitions](../beta-kit/USAGE.md).
Minimum five profiles applies to cohorts and positive counter/tool subgroups.
Unrecorded, suppressed or incomplete evidence stays unknown. Do not relabel
participating profiles as installs, unique users or paid demand.

Reuse the existing HTTPS Registry service and EU PostgreSQL resources. The hosted
candidate mounts the same OSS protocol before Express body parsing, uses an
additive migration and leaves all Footprints/account tables and APIs intact.
Keep collection disabled during migration and verification. Preserve the existing
release governance, database backup and migration ledger controls; do not run all
pending unrelated migrations as a shortcut.

For a standalone, explicitly selected validation database:

```console
node server.mjs --migrate
node server.mjs
node server.mjs --cleanup
```

Supply `RADAR_METRICS_DATABASE_URL` and a private 32-byte hex
`RADAR_METRICS_SECRET` through the operator's secret mechanism. Set
`RADAR_USAGE_ENABLED=1` only after the gates below. The standalone server binds
loopback. HTTP is allowed only with validation environment and explicit local-HTTP
flag; production requires real HTTPS or a reviewed trusted TLS terminator.
Never forward a caller header as authority to disable HTTPS checks.

## Gates before public collection

1. Select a reviewed immutable source revision; reproduce the build, dependency,
   migration, HTTP and existing application checks. Use a disposable PostgreSQL
   database named `forkit_p11_*` for the destructive test suite. No fixtures may
   enter the production metrics tables.
2. Review exact ingress hops, client-address resolution and forwarded-header
   sanitization. Default socket addresses are safer but may put every request
   behind a proxy into one rate bucket. Enable the hosted trust-proxy flag only
   after testing spoofed headers through the real ingress. This follows
   [Express's proxy guidance](https://expressjs.com/en/guide/behind-proxies/).
3. Exclude Authorization, bodies, installation-handle URLs and raw IPs from
   application, nginx, load-balancer, platform request, tracing and export logs
   for these routes. Test a synthetic marker through the actual hosting path
   and inspect every sink. Nginx suppression alone does not control Cloud Run.
   [Cloud Logging routes each entry through independently configured sinks](https://docs.cloud.google.com/logging/docs/routing/overview);
   exclusions occur after ingestion and do not prove the provider never saw
   metadata. Publish any unavoidable residual retention and access restrictions.
4. Schedule `--cleanup` once daily even without requests; alert on failure and
   a last-success age over 24 hours. Contribution bodies older than 35 days are
   eligible and must be removed by 36 days. Manual bodies expire after 31 days.
   Rate-limit hashes older than two hours are removed on maintenance. Live
   withdrawal clears the current body immediately on confirmation.
5. Limit database backups/WAL/export copies to at most 35 days and restrict access.
   A deleted contribution can remain in backups for up to 35 additional days.
   Preserve minimal handle/authentication/sequence/revocation metadata to reject
   replay; do not silently evict it. Keep a recoverable current revocation record.
   Before serving a restored backup, disable intake/public counts, reapply all
   later revocations and cleanup, and verify withdrawn counts cannot reappear.
   If that cannot be proved, keep reporting disabled and clear restored payloads
   in a separately reviewed recovery; do not reset identities or consent.
6. Publish the endpoint, purpose, pseudonymity, exact fields, windows, limits,
   disable/withdrawal steps and operator retention notice. Only then assert
   `RADAR_USAGE_PRIVACY_READY=1` in the hosted integration. This flag records an
   operator decision; it cannot certify infrastructure settings by itself.

The default capacity is 10,000 profiles including tombstones. Default limits are
120 requests/address/hour and 5,000 globally/hour; bodies are capped at 32 KiB.
Alert on repeated unavailable health, cleanup failures, capacity pressure and
fixed-code failure counts without logging personal request details. Fake clients
and multiple profiles remain possible; these are self-reported adoption signals.

## Rollback and recovery

Disable `RADAR_USAGE_ENABLED` first. Local receipt/history functions continue and
queued clients remain bounded. Roll back application revisions independently;
retain the additive tables, secret and revocation data, and keep cleanup running.
Do not drop tables, rotate the secret or revive old payloads as a rollback shortcut.
An unavailable withdrawal remains locally disabled and can be retried after
service recovery. Preserve the secret securely: transparent key rotation is not
implemented and losing it prevents authenticating existing withdrawal requests.

## Release artifacts

Ship only reviewed platform bundles with SHA-256, source revision and dependency
locks. Checksums detect byte changes but do not authenticate the publisher. The
website's release metadata must remain unpublished until actual uploaded files
have been fetched independently and their hashes checked. No speculative PyPI,
npm or curl-to-shell command is a supported installation path. Windows, Intel/x86
and native signed applications are outside this candidate's verified support.
