# Serenity Next baseline and System Console

Baseline observed on 2026-10-02. This is the first Wave 0/1 visibility slice,
not completion of every trust-wave capability.

## Baseline evidence

- The starting workspace commit was `b3d6d61`. The application remains
  Python/FastAPI, SQLAlchemy/Alembic, and plain HTML/CSS/JavaScript.
- Authenticated GitHub inspection confirmed the upstream Serenity repository
  is public, with an untruncated `main` tree. Of 222 baseline application,
  migration, test, script, and documentation blobs compared, 218 matched.
  Only `docs/PUBLISH_ORDERING_REPAIR_PLAN.md`,
  `docs/SERENITY_STATUS_HANDOFF.txt`, `docs/goals-production-review.md`, and
  `replit.md` differed. Application code, migrations, and tests matched.
  No unknown upstream content was overwritten and no raw uploads were copied
  to the public repository. This does not claim the new console is on GitHub.
- The repository has one migration head, `0024_restore_publish_keys`.
  This slice adds no tables, schema migrations, dependencies, startup DDL,
  production DDL, financial corrections, or operational mode switches.
- The handoff records independently checked published Goals metadata and seven
  ownership constraints. That evidence is distinct from signed-in UI proof
  and a fresh managed Publish comparison. No production records, aggregates,
  or schema were queried or changed by this implementation.
- Native exports and disposable recovery rehearsal already exist. A fresh
  disposable PostgreSQL restore test passed during this slice. This is not
  proof of automated encrypted off-host backups, recovery on the chosen host,
  or recoverability of current live records.
- Financial inputs and investment starting positions remain manual.
  Instrument references and hypothetical trading calculations are not live
  feeds or broker execution.

## Using the console

Choose **System** in the authenticated navigation, or open `/system`.
The page calls `GET /serenity-api/system/health`. Both routes require the
existing verified session and workspace authorization, and their responses
are marked `Cache-Control: no-store`, including errors.

The runtime service inspects schema metadata and executes zero-row SELECTs
against registered application tables. These check required columns and read
permissions. The API now also includes separate owner-scoped **Data Health**
readings, described in [DATA_HEALTH.md](DATA_HEALTH.md). Those readings inspect
stored financial inputs through canonical Python services, but return only
bounded explanations, source-page links and record counts, not records, names,
amounts, totals, owner IDs, database locations, credentials or raw exceptions.
No caller-selected workspace changes the report. No privileged repair, restore,
or write-unlock control is exposed.

## Owner-scoped operational history

The later operational-audit slice adds `system_observations` through the
reviewed, additive Alembic revision `0026_system_observations`, after
`0025_projects_tasks`. The original runtime-only baseline above remains
historical evidence, not a claim that the current slice has no persistence.
No startup DDL, production Alembic, or conversion-failure audit is added.

The System page also reads `GET /serenity-api/system/history`, with the same
verified-session, active-owner authorization and `Cache-Control: no-store`
policy. The server derives the workspace from the session. Query parameters
cannot select another owner. Owners see only the observations made through
their own authorized System Console checks, even though underlying runtime
conditions can be shared. This is not a global administrator activity feed.

### Transition and timestamp semantics

- The first successfully retained observation is a **BASELINE**.
- A **TRANSITION** is a change in any member of the fixed tuple:
  overall `state`, database status, schema status, financial write-safety
  status, or migration-tracking status. Migration CURRENT/BEHIND/UNVERIFIED
  changes count even if the overall state stays NORMAL.
- Unchanged refreshes add no event. History reads never generate observations.
  Labels, messages, application versions, revision strings, and check timestamps
  changing on their own do not count. Authentication is already a prerequisite;
  constant backup UNVERIFIED and market MANUAL labels add no history.
- `checked_at` is the UTC completion time of the runtime check, before the
  separate Data Health readings. It is evidence of what that request observed,
  **not** when an outage started, ended, or how long it lasted. SQLite's stored
  naive timestamps are normalized to explicit UTC at the response boundary.
- Requests lock the verified workspace before measuring, then serialize
  comparison and append through commit. This avoids a delayed changed reading
  overtaking a newer unchanged refresh and losing the recovery transition.
  Concurrent identical checks produce one baseline/transition, and a delayed
  check older than the latest retained event cannot reverse newer evidence.
  There is no monitoring loop, synthetic check, heartbeat event, or backfill.
- If authorization fails before a check, no event is recorded. A complete
  database outage may prevent both authorization and audit storage; absence of
  an event is never proof that the app was available. On recovery only newly
  observed evidence can be retained.

### Safe facts and retention

Storage contains only an internal workspace linkage, internal sequence key,
UTC evidence timestamp, BASELINE/TRANSITION kind, and the five allowlisted
status enums. Responses omit the internal linkage and key. No free-form payload
is stored: no secrets, cookie/session identifiers, database URLs or paths,
owner names, financial values or counts, Data Health readings, raw exceptions,
SQL, caller input, application version strings, or revision strings. The
history service emits no raw failure logs. Constraints and response validation
both reject unknown vocabulary rather than echoing damaged stored text.

Retention is **90 days and at most 200 entries per workspace**, newest first.
Every authorized history operation or successful observation attempt deletes
expired operational rows across workspaces and caps the requesting workspace.
Expired rows are not returned. Cleanup is transactional; unavailable storage
returns UNAVAILABLE, not an empty-success result. An idle database can retain
expired physical rows until the next successful authorized console operation;
there is no scheduled purge in this slice. Native backup copies have their
own lifecycle and are not erased by this runtime retention policy. A later
check after all prior evidence expires starts a new baseline, not a claim
about the unseen interval. Workspace deletion cascades this operational
history when the database's foreign-key enforcement is active.

### Failure and authority boundaries

The health response includes `history: {status, recorded}`. AVAILABLE with
`recorded: false` means the current observation added no event (unchanged or
older evidence); UNAVAILABLE means it could not be retained. The UI shows a
save warning separately from current health. A readable but empty history,
unreadable history, and failed history request have distinct messages. Refresh
and session expiry clear previous evidence; delayed responses cannot restore
it. Returned text is never interpreted as HTML.

The optional history table is deliberately excluded from required financial
schema checks. Missing audit storage cannot make a known-good runtime state
unavailable or turn UNKNOWN financial records into empty records. Audit
operations use narrowly scoped Core DML on this table and an identity-preserving
workspace lock; they neither invoke nor bypass any financial mutation API.
Financial write guards remain unchanged, and history can retain READ_ONLY
evidence while financial mutations stay blocked. Health SQL failures are
isolated with a savepoint so a readable audit store can retain an UNAVAILABLE
observation without reusing an aborted PostgreSQL transaction.

### Migration and release review

The new table references only the existing `workspaces.id` primary key; it
adds no financial foreign keys or changes to existing financial tables.
Review the development migration, then apply it through the development
workflow. Use managed Publish's reviewed schema comparison for production:
confirm the new table, enum CHECK constraints, indexes, and workspace
foreign key, with its parent key present before the FK. Do not infer managed
Publish approval from passing Alembic tests. Production runs no migrations.
Downgrade refuses to drop populated history rather than silently deleting it.
This implementation does not publish or inspect live financial records.

Targeted history verification (disposable SQLite/PostgreSQL and synthetic
authorized Chromium fixtures):

```sh
SERENITY_REQUIRE_BROWSER=1 SERENITY_REQUIRE_POSTGRES=1 pytest -q \
  tests/test_system_history.py tests/test_system_history_postgres.py \
  tests/test_system_history_browser.py
```

These tests cover unchanged observations, transitions/recovery, migration-only
changes, evidence timestamps, limits/expiration, isolation, anonymous/expired/
inactive authorization, identity failures, missing/denied storage, rollback
after real PostgreSQL SQL errors, concurrent deduplication, redaction,
financial READ_ONLY enforcement, migration preservation, phone layout, and
browser failure/session clearing. The complete release gate below remains
required; signed-in production UI verification is a separate boundary.

Fresh final full-gate result for this history slice on 2026-10-02:
**1,124 passed, 2 skipped, 2 dependency deprecation warnings**, exit status 0.
Required disposable PostgreSQL and Chromium checks completed. The 37-check
targeted history/console and financial non-mutation run also passed.
The running-app preview still required sign-in; signed-in history behavior was
verified with synthetic authorized browser fixtures, not a live owner session.
Managed production Publish approval and published sign-in remain separate.

| State | Meaning |
| --- | --- |
| NORMAL | Required schema is readable and the existing write guard permits writes at this check. Not a certification of data quality or external systems. |
| READ_ONLY | Required schema is readable, but the existing financial write guard does not permit writes. Existing readable records are not replaced with empty lists. |
| UNAVAILABLE | Database reachability, required schema, read permission, or safety observation could not be established. Unknown is not zero, empty, or lost data. |

The console does not redefine financial mutation rules. Actual writes still
run the existing fail-closed guard, including its transaction-time checks.
Its SQLite and historical-schema policies are unchanged. A displayed
`writes_enabled` value is an observation, not a write authorization or proof
that every constraint has been audited.

If identity tables or the database are unavailable before workspace
authorization completes, the routes return a fixed 503 error rather than
disclosing a health report or bypassing authentication.

## Evidence boundaries

- **Application version:** the running FastAPI application version, not a
  claimed deployed source commit or dependency audit.
- **Schema revision:** known Alembic revisions only. CURRENT means the tracking
  row matches the application's head, not that all constraints were verified.
  BEHIND calls for separate review. Missing, hidden, unknown, duplicate, or
  unreadable tracking rows are UNVERIFIED. Managed Publish applies structure
  independently of this row; its absence does not prove missing data. Never
  stamp or migrate production to make this display green.
- **Authentication:** only the current request passed session and workspace
  authorization. The console does not verify published sign-in, invitation
  policy, or provider-wide availability.
- **Backups:** UNVERIFIED for actual off-host protection and host recovery.
  Disposable rehearsal capability is described separately.
- **Financial/market provenance:** MANUAL, with no live feed or broker claim.
- Runtime schema readability is not a row-level data-quality audit. Separate
  Data Health readings identify specific input evidence without claiming all
  records or real-world holdings are complete. No arbitrary health score or
  synthetic empty financial summary is generated.

Refresh removes previous evidence before requesting another observation.
Network errors, bad JSON, malformed or contradictory responses, and HTTP
failures show UNAVAILABLE rather than retaining a healthy badge. Session
expiry and inactive-account responses clear console evidence and use the
existing session recovery screen. The page supports phone navigation and
reduced motion, and renders returned text without interpreting it as HTML.

## Verification and release

The original runtime-only slice's targeted suite passed: **26 tests**, including owner isolation,
anonymous rejection, identity-schema failure, missing tables/columns,
redacted failures, allowlisted revisions, disposable PostgreSQL staging and
restoration, denied SELECT permission, and Chromium state/refresh/session/
phone checks. A separate required PostgreSQL native restore test passed.

The signed-in console was tested and visually inspected using synthetic
authorized fixtures only. The running-app screenshot reached the sign-in
page without removing authentication. Published sign-in remains unverified
by this slice.

Required complete gate:

```sh
bash scripts/prepublish_check.sh
```

Fresh full-gate result on 2026-10-02: **1,000 passed, 2 skipped, 2 dependency
deprecation warnings**, exit status 0. Mandatory disposable PostgreSQL and
Chromium checks completed. No existing database was migrated by this gate.
The optional PostgreSQL restore check that this gate skips was separately
required and passed above; published sign-in was not exercised.

Targeted reproduction:

```sh
SERENITY_REQUIRE_BROWSER=1 SERENITY_REQUIRE_POSTGRES=1 pytest -q \
  tests/test_system_health.py tests/test_system_health_postgres.py \
  tests/test_system_browser.py
SERENITY_REQUIRE_POSTGRES_RESTORE=1 pytest -q \
  tests/test_backup_restore.py::test_postgres_native_roundtrip_when_required
```

All destructive schema fixtures and financial test inserts use disposable
databases. Production access and managed Publish approval remain separate
human-reviewed operations. This slice does not publish the application.