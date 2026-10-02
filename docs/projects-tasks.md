# Projects and Tasks

Projects and Tasks are owner-private work records in the approved Personal OS
wave. Projects may optionally support one Goal; Tasks may optionally belong to
one Project. Either can stand alone. There is no Initiative table, automatic
Goal progress, financial posting, or valuation change.

## Boundaries and lifecycle

- Tasks are actions, not Goal Items. They have no expected cost, actual cost,
  amount, allocation, financial source, or scenario fields.
- Due/target dates are work intentions, not proof of actual financial events.
  Status and backend UTC completion time record manual work state only.
  ACTUAL, PLANNED, PROJECTED and SCENARIO financial sources remain unchanged.
- Status is `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED`, `PAUSED`, or `CANCELLED`.
  New work starts `NOT_STARTED`. Completion is an explicit status action;
  repeated completion retains its timestamp, leaving completion clears it.
- Priority is user-set `HIGH`, `NORMAL`, or `LOW`, not derived Attention.
- Archive/reactivate is separate from status. Neither cascades to children or
  changes parent Goal/Project state. Archived work is readable, not editable.
  Tasks within an archived Project are read-only until that Project is restored.
  An existing Project link to an archived Goal may be kept or removed; an archived
  Goal cannot receive new Project links.
- PUT replaces editable fields, including an explicit optional source link.
  Ownership, status, archive state and timestamps are rejected in edit payloads.
  Names are required, text is bounded, source IDs are strict positive integers.

## Isolation and persistence

Authentication resolves the internal workspace, following existing Goals
ownership conventions. Owner IDs are never caller-selected or returned in
read models. Services scope every read/write/source lookup; missing and
foreign-owned IDs both return 404.

Composite RESTRICT foreign keys enforce `(owner_id, goal_id)` and
`(owner_id, project_id)`. Narrow SQLite guards enforce the same relationships
under the existing runtime connection policy, without changing financial-table
PRAGMAs. Source rows are locked during relationship writes; SQLite reserves the
writer before reading. Goal deletion returns 409 while any Project remains
linked, including archived work. Unlink deliberately; no silent cascade.

Development migration `0025_projects_tasks` adds only two work tables and their
indexes/guards. Downgrade checks both tables before dropping either and refuses
if any work exists. Stop writers for SQLite schema maintenance. PostgreSQL
locks source/work tables during downgrade preflight. Never run production
Alembic or startup/publish schema hooks.

## API, screens and portability

Authenticated `/serenity-api/projects` and `/serenity-api/tasks` each support
GET list/options/single record, POST create, PUT edit, and explicit POST
`/{id}/status`, `/deactivate`, `/reactivate`. Lists default to active-only;
`active_only=false` includes archives. Projects accept a `goal_id` source
filter; Tasks accept a `project_id` source filter. Source names load in batches.
Errors are 404 (inaccessible source/record), 409 (lifecycle/relationship conflict)
or 422 (invalid input).

`/projects` and `/tasks` provide create/edit/cancel, detail reads, status,
archive/reactivate, archived visibility and source filtering. Goal details link
to Projects; Project details link to Goal and Tasks; Task details link to Project.
Deep links select the source rather than duplicating it into another entity.

Workspace JSON export adds owner-scoped `projects` and `tasks`, including
archives, without changing format version 7 or existing financial meanings.
Transaction CSV is unchanged. No import/restore workflow is added by this slice.

Verification: `bash scripts/prepublish_check.sh` runs the entire suite, including
disposable PostgreSQL, SQLite raw constraints, downgrade preservation, financial
invariance and real Chromium create/edit/status/archive/source-navigation checks.