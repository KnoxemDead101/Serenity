# Published Goals: read-only progress review

## Authorization and scope

The user explicitly authorized a read-only, aggregate-only check of published
Goal data. This authorization did not permit any record or configuration changes.
The earlier development review found an existing Goals table with zero records;
that result does not establish the state of published data.

## Storage and observed result

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

## Current application rule

Reviewed `models/goal.py`, `schemas/goal.py`, `services/goal_service.py`,
`frontend/static/js/goals.js`, and `utils/choices.py`.

- Only `MANUAL` progress uses a stored current progress amount. Other sources
  are reserved metadata, not linked or automatically calculated progress.
- Create/update input validation rejects a non-MANUAL source paired with any
  non-null progress amount, including zero; the form also blocks submission.
- The model constrains amounts and source choices separately, but does not
  include a database check coupling the source to the amount.
- The service preserves null versus zero and returns existing stored amounts;
  it does not silently repair unsupported historical combinations.
- These are workspace code observations, not proof of which version or rule
  is enforced by the current published build.

No verified production enforcement cutoff was established. Commit dates were
not used to exclude records.

## Count definition for a later authorized check

If the published table becomes visible, first confirm its existence again,
then use a read-only aggregate query:

```sql
SELECT
    COUNT(*) AS affected_total,
    COUNT(*) FILTER (WHERE active IS TRUE) AS affected_active,
    COUNT(*) FILTER (WHERE active IS FALSE) AS affected_archived
FROM public.goals
WHERE progress_source <> 'MANUAL'
  AND current_progress_amount_cents IS NOT NULL;
```

This query was **not executed**. It includes active and archived Goals, all
dates, and non-null zero amounts. It returns record counts only: no names,
notes, IDs, owner identities, individual amounts, or financial totals.

## Handling any affected records

Recommend individual owner review if affected records are found. Preserve each
record while its meaning is uncertain. Changing a source to `MANUAL` or clearing
an amount requires explicit authorization; this check does not authorize either.

No records were cleared, relabeled, deleted, migrated, or rewritten. No database
configuration or storage was changed. No automatic progress, Goal Composition,
or Transaction linkage was implemented or modified.