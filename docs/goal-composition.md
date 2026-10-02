# Goal Composition

Goal Items, Milestones and Checkpoints are owner-private planning records,
introduced by `0019_goal_composition` after `0018_goal_core`. They do not create
Transactions, allocations, cash movement, expenses, income or debt activity.
Nothing here links a Transaction to a Goal. Financial services, financial totals
and the Transaction spreadsheet export are unchanged.

## Money and lifecycle

- Item expected cost and manual actual-cost override are separate optional
  **integer-cent BIGINT** columns. The override is provisional planning input,
  never evidence of real spending. A future, separately authorized linkage must
  make Transaction-derived actual cost take precedence, not add it to this value.
- API money inputs use validated decimal dollars and outputs include dollar
  strings and raw cents, matching Goal Core. There are no floating-point or
  decimal money columns.
- Item statuses: `PLANNED`, `IN_PROGRESS`, `COMPLETED`, `SKIPPED`, `CANCELLED`.
  Items can also be archived/reactivated independently of status.
- Milestone statuses: `NOT_STARTED`, `IN_PROGRESS`, `COMPLETED`, `SKIPPED`,
  `CANCELLED`. The backend sets UTC completion time on entry to `COMPLETED`,
  preserves it on a repeated completion action, clears it when leaving
  `COMPLETED`, and assigns a new time on later completion.
- Child status never changes parent Goal status, progress or completion time.
  General PUT payloads cannot change status, owner, parent, archive state,
  timestamps or checkpoint reached state. Status/archive use explicit actions.
- `sort_order` is a nonnegative integer. Records sort by `(sort_order, id)` so
  ties remain stable. Reordering is an ordinary validated order-field edit, not
  an automatically recalculated financial operation.
- Checkpoint reached is computed on every read: meaningful `MANUAL` Goal
  progress is compared with the checkpoint's integer cents. Missing manual
  progress gives `null` / Unknown, not an assertion that a checkpoint was
  reached or missed. Reserved sources do not supply automatic progress.
  No reached flag is stored. Lowering progress can make a marker unreached.

## Ownership, parent deletion and downgrade safety

Each child uses the repository's existing composite relationship:
`(owner_id, goal_id) -> goals(owner_id, id)`, with `ON DELETE RESTRICT`, matching
Portfolio-owned child records. Services also validate the authenticated owner
and parent before every child read, write and reorder; IDs from another parent
or workspace are inaccessible. An archived parent is readable but its
composition is read-only until the Goal is reactivated.

Goal deletion returns **409** while **any** child exists, including an archived
Item or cancelled Milestone. Users must deliberately delete the child planning
records before deleting the Goal. There is no silent cascade and no ORM
delete-orphan behavior. Parent locking serializes child writes and deletion on
PostgreSQL; database relationships provide the additional constraint boundary.
SQLite Goal mutations reserve the writer with `BEGIN IMMEDIATE` before reading
the parent, because SQLite ignores `FOR UPDATE`. This serializes API child
writes with parent deletion without altering shared connection configuration.
Existing SQLite connections leave native FK enforcement off. SQLite-only
database guards additionally enforce the same composite owner/Goal relationship
for child INSERT/owner-parent UPDATE, prevent raw parent deletion while children
exist, and prevent changing a parent's identity with attached children. They
cover only Goal tables, not financial tables, and do not change shared PRAGMAs.
PostgreSQL uses its ordinary composite FK directly.
The deletion guard counts all rows attached to the owned Goal, even malformed
owner metadata, rather than allowing an orphan if legacy constraints were off.

Downgrading to `0018_goal_core` checks **all three tables before any drop** and
fails with a clear error if any child records exist, even archived or cancelled
ones. PostgreSQL takes exclusive locks on the parent and all three child tables
in parent-first order during this preflight. Parent
Goals alone do not prevent an otherwise safe downgrade: they remain intact.
Offline SQL downgrade fails clearly because it cannot verify that tables are
empty. SQLite parent guards are dropped only after the preservation preflight
passes; child guards disappear with their empty tables. As with existing SQLite migrations, maintenance must run with app writers
stopped. This preserves planning data rather than destroying it to make a
downgrade succeed.

## API and loading

Authenticated routes under `/serenity-api/goals`:

- `GET /composition/options` provides the two status vocabularies.
- `GET /{goal_id}/composition` returns the Goal and all three child collections.
  `active_only=false` includes archived Items; Milestones and Checkpoints are
  always included.
- `/{goal_id}/items`, `/milestones`, `/checkpoints` support list/create and
  single-record GET/PUT/DELETE.
- Items and Milestones have `POST /{record_id}/status`.
- Items have `POST /{record_id}/deactivate` and `/reactivate`.

Routes are thin authenticated wrappers over focused composition services.
The normal Goal list does not load children. Opening Details loads one Goal
query plus one bounded collection query per child family, not one per record.
There is no caching, background work or asynchronous infrastructure.

## JSON export compatibility

Full-workspace JSON stays at **format version 6**. Each existing Goal dictionary
gains `items`, `milestones` and `checkpoints` arrays. Existing keys and values are
not removed, renamed or reinterpreted. Consumers ignoring additional fields
remain compatible; no incompatible format change warrants a version increase.
Archived Items and all Milestones/Checkpoints are included, owner-scoped and
stably ordered. Derived checkpoint `reached` is omitted from backup state.
Export loads each child family in one batch across the workspace instead of
fetching it separately for each Goal.