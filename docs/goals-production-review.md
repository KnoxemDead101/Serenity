# Published Goals: read-only progress review

## Fresh rollout verification after owner-reported publication (2026-10-02)

The owner reported all publications approved and requested continuation of
Serenity Next. The owner then separately authorized a fresh aggregate-only
production Goals check and post-publication schema-only inspection.
Deployment metadata confirmed an active, successful private Autoscale build.

The fixed metadata check returned READY for `public.goals` and all required
columns. Only after that confirmation, the exact aggregate query below ran
against `environment: "production"`, `target: "replit_database"`. Results were
zero affected total, active, archived, and non-null zero-amount rows. All dates
were included; no Goal identities, details, amounts, or financial totals were
retrieved. These are affected counts, not total Goal counts.

Schema-only catalog inspection confirmed `ck_goals_manual_progress_only` on
`public.goals`, type CHECK, validated, with definition:

```sql
CHECK ((((progress_source)::text = 'MANUAL'::text)
        OR (current_progress_amount_cents IS NULL)))
```

The same separately authorized inspection confirmed all seven restored
ownership foreign keys documented in `PUBLISH_ORDERING_REPAIR_PLAN.md`,
including owner-matched columns, referenced parents, `ON DELETE RESTRICT`,
and validated status.

This establishes observed production-replica enforcement, not signed-in UI,
live runtime connection, backup readiness, or a fresh pre-publication preflight.
Publication preceded this check; post-publication evidence cannot retroactively
establish the required fresh preflight or the exact comparison approved during
publication.

The fresh managed Publish comparison operation was unavailable in this agent
session. The retained fixture is historical review/test evidence, not a fresh
comparison. The owner was asked for a credential-free Publishing summary
covering the Goals check, reviewed index removals, other changes/warnings,
and overwrite-data being off, and replied **"Confirmed"**. This is owner
confirmation of the requested checklist, not an independently retrieved SQL
plan or a detailed UI capture. No additional publication was initiated.

The observed enforcement verification is complete after the owner's reported
publication. The rollout sequence differs from the planned pre-publication
review: fresh aggregate evidence was collected afterward and cannot prove the
pre-publication data state. Preserve this qualification in release handoffs.

No records, production schema, deployment commands, or storage settings were
changed. No production Alembic, DDL, schema hook, or financial test insert ran.

The fresh full validation command `bash scripts/prepublish_check.sh` completed
successfully: **974 passed, 2 skipped, 2 dependency deprecation warnings**.
It exercised disposable PostgreSQL and browser checks without migrating an
existing database. A foreground attempt reached the shell time limit; the
complete background run exited zero. Neither run inspected production data.

## Opt-in schema check after each future publication

Ask the agent: **“Check the published Goals schema using production read-only
metadata only.”** This is a separate post-publication operation. It is never
run by startup, the Run button, the prepublish gate, or the deployment build.
No deployment configuration or storage selection is changed. The existing
`.replit` deployment command is intentionally unchanged.

The check verifies `public.goals` and **all columns used by the Goal model**,
not only the three columns used by the historical aggregate review below.
It queries PostgreSQL catalogs and `information_schema` only, through Replit's
`executeSql` with `environment: "production"` and `target: "replit_database"`.
It never reads Goal rows, counts, identities, amounts, connection strings, or
credential values. It does not use `DATABASE_URL` or local SQLite. It applies
only to the project's intended Replit-managed production database; if storage
selection changes to an external database, stop and reassess the target.

### Agent/operator procedure

1. Confirm that the owner has finished publishing and that deployment metadata
   reports a successful current build (`getDeploymentInfo`). If unavailable,
   failed, or still building, report readiness unavailable; do not claim the
   new publication has been checked.
2. Obtain the fixed query with
   `python scripts/check_goals_schema.py --print-query`. Execute it with the
   production read-only database tool. Do not run the query through a shell
   database client, a caller-provided URL, or the app engine.
3. Pass the tool result to the evaluator as shown below. The envelope is
   created immediately from the actual tool invocation, not a development
   result relabeled as production or a hand-edited result. It is an operator
   provenance assertion, not a signed attestation. Do not retain or print raw
   failed tool output: it might include connection details.
4. If metadata is missing on a replica, wait 30 seconds and repeat steps 2–3
   with a fresh result, up to three attempts total. A tool/permission failure
   is unavailable, not a missing table. After bounded retries, leave readiness
   blocked and explain that lag or unapplied Publish schema may be responsible.
   The replica cannot establish which. Ask for a credential-free Publishing
   schema review; never automatically publish or “repair” the database.

Example for the agent's callback execution environment (not a shell command):

```javascript
const query = await shellExec({
  command: "python scripts/check_goals_schema.py --print-query"
});
if (query.exitCode !== 0 || query.truncated) throw new Error("Query unavailable");
const result = await executeSql({
  environment: "production",
  target: "replit_database",
  sqlQuery: query.output.trim(),
  params: []
});
// The evaluator outputs only allowlisted schema names and fixed messages.
// A failed result is redacted before crossing into a shell process.
const envelope = {
  environment: "production",
  target: "replit_database",
  checked_at: new Date().toISOString(),
  result: result.success && result.exitCode === 0
    ? { success: true, exitCode: 0, output: result.output }
    : { success: false, exitCode: 1, output: "" }
};
const payload = Buffer.from(JSON.stringify(envelope)).toString("base64");
const report = await shellExec({
  command: "printf '%s' '" + payload +
    "' | base64 -d | python scripts/check_goals_schema.py --production-metadata"
});
console.log(report.output);
```

Each retry must call `executeSql` again; do not re-evaluate a saved success.
The evaluator rejects evidence older than five minutes, future-dated evidence,
wrong targets, malformed results, and unexpected column names. No input flag
means usage failure, not a database check. There is no fallback to another
database when production is unavailable.

### Interpreting the result

| Result / exit code | Meaning |
| --- | --- |
| `READY (schema only)` / 0 | The Goals table and every required column are present and visible in the observed production connection. |
| `MISSING` / 1 | A table or required columns are absent in that connection's catalog. On a replica, allow catch-up and repeat before escalating. |
| `UNAVAILABLE` / 2 | Fresh production metadata cannot be verified, or objects exist but metadata visibility is insufficient. |

Missing or unavailable storage is **unknown data, never zero/empty Goals**.
Even READY does not establish whether any Goal records exist. Replica success
is an observation of schema presence/visibility, not proof of primary state,
the running app's connection, or its source version. The check intentionally
does not certify types, constraints (including progress protection), existing
data validity, authenticated Goals behavior, published sign-in, or backups.
Those require separate checks and authorization. Never bypass private
publication or app authentication to perform this check.

Any schema action belongs to the supported Publish review with separate owner
approval. Do not run production DDL/Alembic, add deploy/startup migration hooks,
replace storage, select overwrite-data, or change/clear any financial record.

### Implementation verification (2026-10-02)

The opt-in procedure was exercised against the managed production read-only
replica after deployment metadata confirmed a successful current publication.
It returned **READY (schema only)** for `public.goals` and all 17 required
columns. No Goal rows were read. This observation is not a standing readiness
certificate for later publications.

Disposable PostgreSQL regression checks separately cover a missing table,
partial columns, visible complete schema with either empty or populated data,
restricted metadata visibility, and a metadata-visible role with no SELECT
privilege on Goals. Offline report checks cover freshness, wrong targets,
malformed evidence, redacted failures, and explicit opt-in.

## Latest result after owner-reported publication

The owner reported, "Published successfully, continue next steps." The agent
did not initiate publication or change deployment/storage configuration.
Deployment metadata then confirmed an active, successful private Autoscale
publication. The production read-only PostgreSQL connection confirmed
`public.goals` exists, all three required columns are visible, and the
connection is a replica (`pg_is_in_recovery() = true`).

With the owner's renewed aggregate-only authorization, the query documented
below was executed successfully against `environment: "production"`:

| Affected records | Count |
| --- | ---: |
| Total | 0 |
| Active | 0 |
| Archived | 0 |
| With a non-null zero progress amount | 0 |

The exact predicate was `progress_source <> 'MANUAL' AND
current_progress_amount_cents IS NOT NULL`. Active and archived records,
non-null zero amounts, and all dates were included. No enforcement cutoff was
assumed. These are counts of unsupported source/amount combinations, **not**
a count of all Goals. No individual records, identities, financial amounts,
or financial totals were retrieved.

The observed storage is the Replit-managed production PostgreSQL replica, not
local SQLite or development. The current deployment command and runtime-managed
database selection are consistent with that storage. The earlier absence was
a real schema difference in the replica, not ordinary table-permission
filtering; it resolved after the owner-reported publication. The available
evidence does not distinguish when Publish applied the schema from when its
replica caught up. It also does not independently inspect the running app's
connection or verify the signed-in Goals UI. No authentication bypass or
credential access was attempted.

All records were preserved by this review. No source was changed and no
amount was cleared. No automatic progress, Goal Composition, or Transaction
linkage was added. The sections below retain the earlier diagnostic sequence;
their unavailable-count and blocked-check statements describe the state
**before** this successful post-publication check.

## Authorization and scope

The user explicitly authorized a read-only, aggregate-only check of published
Goal data. This authorization did not permit any record or configuration changes.
The earlier development review found an existing Goals table with zero records;
that result does not establish the state of published data.

## Initial storage and observed result (before publication)

The deployment metadata confirmed an active published deployment with a successful
build. Project instructions identify Replit-managed PostgreSQL as production
storage; the production run command does not override the database with local
SQLite. Queries used the database tool's `environment: "production"` read-only
replica, not the local SQLite file or development database.

Both metadata queries succeeded:

```sql
SELECT EXISTS (
    SELECT 1
    FROM information_schema.tables
    WHERE table_schema = 'public'
      AND table_name = 'goals'
      AND table_type = 'BASE TABLE'
) AS goals_table_exists;
-- Result: false

SELECT COUNT(*) AS goals_tables_visible
FROM information_schema.tables
WHERE table_name = 'goals'
  AND table_type = 'BASE TABLE';
-- Result: 0
```

**Limitation:** No Goals table is visible to the production read-only connection.
The unsupported-combination count is therefore **unavailable, not zero**.
The metadata result alone cannot distinguish a missing production table from
restricted visibility or replica differences. No Goal-row query was attempted
after the table-existence check failed.

## Follow-up storage diagnosis (2026-10-02)

Read-only deployment metadata reports an active, successful **private**
Autoscale publication. The current workspace deployment command in `.replit`
runs Uvicorn without a SQLite override. The database
selector uses `DATABASE_URL` when present; the environment metadata identifies
that key as runtime-managed and present for production. No credential value
was accessed. Project instructions identify managed PostgreSQL as intended
production storage. The explicit SQLite override belongs to local development.

These observations establish the intended/current workspace configuration,
**not independent verification of the running published process's database
connection or its deployed source revision**. The private publication was not
accessed with a signed-in session or bypassed.

Additional schema-only queries returned:

```sql
-- Production read-only connection; no Goal rows accessed.
SELECT
    EXISTS (
        SELECT 1
        FROM pg_catalog.pg_class c
        JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
        WHERE c.relname = 'goals' AND c.relkind IN ('r', 'p')
    ) AS goals_in_catalog,
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_name = 'goals' AND table_type = 'BASE TABLE'
    ) AS goals_visible,
    pg_is_in_recovery() AS is_replica;
-- false, false, true

-- Managed development connection; schema existence only, no row counts.
SELECT EXISTS (
    SELECT 1
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public'
      AND c.relname = 'goals' AND c.relkind IN ('r', 'p')
) AS public_goals_in_catalog;
-- true
```

The catalog result rules out ordinary `information_schema` privilege filtering
as the explanation in this replica: no ordinary or partitioned Goals table is
present anywhere in its catalog. There is a development/production-replica
schema difference. An unpublished schema or replica lag remains possible;
neither its cause nor live-primary table absence is proven by these results.
Counts remain **unavailable, not zero**.

Next steps require separate owner decisions:

1. Confirm the live publication's database selection in Publishing without
   sharing credentials. If managed PostgreSQL is confirmed, review its
   development-to-production schema changes using the supported Publish UI.
   Obtain separate authorization before any publication/schema action.
   Do not select overwrite-data, approve destructive changes, add startup DDL,
   or run production Alembic as part of this diagnosis.
2. Obtain renewed explicit permission for a read-only aggregate-only check.
   Reconfirm table existence and required columns before executing it.
   Report total, active, archived, and zero-amount affected record counts
   using the exact predicate below and all dates. No enforcement cutoff
   has been verified.

No publication, migration, configuration change, or Goal-row query occurred
during this follow-up diagnosis. The aggregate check is still incomplete.

### Renewed authorization and initially blocked Publish review

The owner renewed explicit permission for both the read-only Publish schema
comparison and the production aggregate-only check. This did **not** authorize
publishing, schema changes, configuration changes, or record corrections.

The renewed production catalog check returned `public_goals_exists = false`,
`goals_any_schema_exists = false`, and `is_replica = true`. Consequently the
aggregate query was again not executed. All affected counts remain unavailable.

The documented read-only Publish comparison operation was unavailable in this
agent session; no comparison ran and no schema changes were applied. This is
not evidence that the schemas match or that publishing is safe.

At that point, completion was blocked pending a credential-free Publishing UI confirmation of
the live storage selection and its pending schema-change summary. Review any
drop, truncate, destructive alteration, or rename carefully; never select
overwrite-data. Any actual publication requires separate owner approval and
the supported Publish process. Afterward, reconfirm table and column existence
before the authorized aggregate-only query. This task must not be reported as
complete while live storage and aggregate results remain unverified.

## Current application rule

Reviewed `models/goal.py`, `schemas/goal.py`, `services/goal_service.py`,
`frontend/static/js/goals.js`, and `utils/choices.py`.

- Only `MANUAL` progress uses a stored current progress amount. Other sources
  are reserved metadata, not linked or automatically calculated progress.
- Create/update input validation rejects a non-MANUAL source paired with any
  non-null progress amount, including zero; the form also blocks submission.
- The model constrains amounts and source choices separately, but does not
  include a database check coupling the source to the amount in the version
  examined during that production review. The development safeguard below
  supersedes that workspace observation, not the historical production evidence.
- The service preserves null versus zero and returns existing stored amounts;
  it does not silently repair unsupported historical combinations.
- These are workspace code observations, not proof of which version or rule
  is enforced by the current published build.

No verified production enforcement cutoff was established. Commit dates were
not used to exclude records.

## Executed aggregate count definition

After the owner reported publication, the production table and required
columns were confirmed before executing this read-only aggregate query:

```sql
SELECT
    COUNT(*) AS affected_total,
    COUNT(*) FILTER (WHERE active IS TRUE) AS affected_active,
    COUNT(*) FILTER (WHERE active IS FALSE) AS affected_archived,
    COUNT(*) FILTER (
        WHERE current_progress_amount_cents = 0
    ) AS affected_zero_amount
FROM public.goals
WHERE progress_source <> 'MANUAL'
  AND current_progress_amount_cents IS NOT NULL;
```

This query was **executed successfully after publication**. It includes active and archived Goals, all
dates, and non-null zero amounts. It returns record counts only: no names,
notes, IDs, owner identities, individual amounts, or financial totals.

## Handling any affected records

Recommend individual owner review if affected records are found. Preserve each
record while its meaning is uncertain. Changing a source to `MANUAL` or clearing
an amount requires explicit authorization; this check does not authorize either.

No records were cleared, relabeled, deleted, migrated, or rewritten. No database
configuration or storage was changed. No automatic progress, Goal Composition,
or Transaction linkage was implemented or modified.

## Development persistence safeguard (2026-10-02)

The owner separately authorized code, tests, and development schema work.
The model and migration `0023_goal_progress_guard` now declare the named check
`ck_goals_manual_progress_only`:

```sql
CHECK (progress_source = 'MANUAL' OR current_progress_amount_cents IS NULL)
```

The authorized development PostgreSQL upgrade completed successfully at this
revision, and schema inspection confirmed the named check. No production
connection was queried or migrated during this development work.

This permits MANUAL null, zero, and valid positive amounts, and reserved sources
only with null amounts. Existing source-choice and amount-range checks remain.
It applies to direct inserts and updates, including source-only changes and
archived Goals, not just form/API submissions.

Development Alembic preflights all historical Goals, serializing PostgreSQL
writes during enforcement. It refuses incompatible data without printing record
details, clearing amounts, or relabeling sources. SQLite runs as a maintenance
operation with writers stopped; its transactional parent rebuild preserves
existing child records, indexes, constraints, and Goal relationship triggers.
Downgrade removes only the new check and preserves records.

### Production rollout remains separately gated

This authorization does **not** approve publication, production record queries,
or data corrections. The prior zero counts above are historical observations,
not a fresh rollout preflight and not assurance that no affected rows exist now.

Before any rollout:

1. Obtain renewed explicit authorization for the read-only aggregate-only query
   above; reconfirm the production table and required columns first. Include all
   dates, active/archived records, and non-null zero. Do not retrieve record details.
2. If any affected rows exist, stop. Preserve them and request a separately
   authorized owner correction plan; do not clear amounts or change sources.
3. Apply/review the development schema using the existing development Alembic
   flow, then review the actual Publish comparison. Confirm it carries the named
   check without destructive record/table operations or unrelated schema changes.
   If the comparison is unavailable, obtain a credential-free UI summary.
4. Obtain separate production publication approval and use managed Publish.
   Never run production Alembic, direct production DDL, startup/build schema
   hooks, or overwrite-data. Publish validates existing rows when adding the
   check; the development preflight is not a production migration script.
5. After publication, verify the named production constraint through a separately
   authorized schema-only check. Do not test by inserting financial records.

No automatic progress, new composition, or transaction linkage is part of this
safeguard. Existing composition must remain unchanged.