# Approved investment conversion: execution design

**Status:** implementation-ready proposal, not execution authorization. This document
does not change schema, balances, valuation, or the read-only API. Phase 2 design
approval and the authorization for organization-only containers do **not** authorize
this slice, a real conversion, deletion, source push, or publication. Obtain separate
implementation approval and then separate, explicit owner approval of each exact
real-data report and correction before execution.

Normative inputs: [Phase 2 scope](PORTFOLIO_PHASE2_SCOPE.md) and the
[read-only reconciliation contract](RECONCILIATION_API.md). The current
`/serenity-api/reconciliation/preview`, `/verify`, and `/export` endpoints remain
read-only; a signed preview token is evidence, **not** an approval or an execute
credential. These designs assume an authenticated workspace owner, not a client
supplied `owner_id`.

## Prerequisites and release boundaries

1. Add only empty schema first, with explicit migrations. Startup, Alembic, and
   deployment must never convert existing rows, infer instruments, correct cash,
   or enable new valuations. Downgrade should refuse when conversion history is
   present; never discard evidence to make downgrade succeed.
2. Preserve legacy create/update/delete/reactivate behavior for **unconverted**
   investments. Build the new shared valuation selection and cash calculation
   paths before enabling execute. Every dashboard, finance summary, account
   balance, export, and future activity reader must use the same rules. Feature
   gating must fail closed if any reader still uses the legacy total indiscriminately.
3. Before production use, require the separate backup workstream to provide
   automated encrypted off-host backups, restricted/recoverable keys, a recent
   native backup of the intended database, and a successful isolated restore
   rehearsal on the intended host/version. Record a private backup evidence
   reference, observed timestamp, schema revision and agreed rollback window in
   the conversion approval. A local synthetic rehearsal or JSON export is not
   this gate. Do not implement backups in this slice; see
   [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Fail closed if evidence is absent,
   outdated for the agreed window, or does not cover the pre-conversion state.
   The operator must establish the backup cutoff and quiescence policy for
   concurrent writers before approving a real batch. Backups are disaster
   recovery; the targeted reversal below is not a replacement.

## Durable data model (proposed)

Every new row has a non-null workspace owner; use owner-scoped lookups and
composite `(owner_id, id)` parent keys/FKs for source, portfolio/container, cash
account, instrument and exact specification where practical, plus service checks.
No ticker-only resolution. Monetary values are signed BIGINT integer cents,
quantities are the existing scaled BIGINT units. Validate bounds and sums before
writing.

| Record | Required persisted facts and constraints |
| --- | --- |
| `reconciliation_approvals` | ID, owner, immutable canonical report bytes (or losslessly equivalent JSON), format/version, SHA-256 digest of canonical bytes, original signed token envelope or verified signature evidence, preview cutoff and source fingerprint, approving authenticated actor, approval timestamp, explicit approved source IDs and account correction amounts, approved before/after component totals and delta, backup evidence reference/cutoff, rollback deadline, state (`approved`, `executed`, `reversed`, `expired`), execution/reversal timestamps. Unique owner+report digest for this approval; no edits to content after approval. Restrict full report access/export to the owner; never log its contents. |
| `opening_positions` | ID, owner, approval ID, unique source investment ID **across all conversions including reversed ones**, container/account/portfolio at approval, verified instrument ID and pinned immutable specification ID/version, quantity units, entered basis cents plus `unknown`/`unverified` status and reviewed-zero evidence, original entered value cents, valuation provenance/evidence and nullable actual as-of date, capture timestamp, source edit timestamp, nullable acquisition date (unknown), immutable exact source snapshot (ID, owner, active, name, ticker, quantity, basis, value, notes, created/updated), status (`active`/`reversed`). One opening position per converted source; source snapshot is never overwritten. Keep the source row itself, even after reversal. |
| `valuation_eligibility` | One owner+source link to the opening position, with active representation `legacy` **or** `opening`, never both; immutable audit transition on conversion/reversal. A missing link means legacy behavior. For converted sources, legacy is read-only and excluded, replacement is counted only if the source was active and personally owned in the approved report. An inactive source requires separate reactivation approval and cannot be converted in this batch. A reversed link retains history but selects the restored legacy representation. DB uniqueness/checks and read-side join enforce one selection, not two booleans that can both be true. |
| `cash_reconciliation_entries` | Owner, approval, account, signed delta cents, reason `combined_balance_overlap` (later `conversion_reversal` references the original), evidence, before/after calculated account balances, creation/actor/time and unique approval+account+reason; immutable append-only, with reversal by compensating entry. No Income/Expense `Transaction`, no category or merchant, no change to the account's original `opening_balance_cents`. |
| `conversion_events` | Owner, approval, event kind, canonical before/after totals and per-source/account state, cutoff, timestamp, actor, report hash, backup evidence reference, linked IDs and failure/reversal reason if applicable. Append-only. A committed conversion and its event share a transaction. Failed attempts can be recorded separately without exposing data or claiming execution. |

Indexes on owner+approval/status and owner+source support audit and uniqueness.
Guard immutable rows against application edits/deletes; do not cascade-delete the
source, report, cash entry, or specification. Add owner-matched unique keys to
existing parents if needed without rebuilding or rewriting financial data.
Reference specifications remain readable after archive.

## Preview, approval and execution contract

The existing report format 1 and signed token remain read-only. Introduce a
versioned **execution-capable report** only after the new ledger/valuation logic
can compute exact results; do not silently execute old tokens. It may reuse the
request declarations and preview UI, but must state its executable format/version,
algorithm version, all owner dependencies and expected before/after component
totals. The read-only endpoints can continue to accept historical format 1 for
review only. If a new report cannot reproduce the current preview semantics, stop
and require fresh review rather than reinterpret an old report.

The execution report must enumerate every source (including unmapped and
inactive), every account, linked containers, instrument/specification rows,
transactions/corrections, debts, existing openings, corrections, eligibility and
activity, and the declared completeness evidence. Show per-source eligibility,
cash-only versus combined meaning, basis status, original entered value and
provenance, confirmed personal ownership, all warnings, expected corrections,
current/proposed totals and explained delta. Keep unresolved sources on their
legacy path, flagged; never count an opening over an unresolved combined balance.
For each affected account, require explicit `complete=true` attestation that
`source_ids` cover **all** represented securities in that account, not just
the selected batch. Existing legacy investments have no account relationship;
do not infer completeness from the database. If a source in that declared
account group is unresolved/inactive, refuse that account's conversion. For
`cash_only`, evidence must reconcile cash cents to current calculated balance;
for `combined`, require current balance = cash cents + sum of *all* declared
original security values, and correction = negative of that sum. Never reduce
cash by the partial selected subset. Reject no-op/empty executable batches.
If a later batch involves an account with prior corrections, produce a fresh
report whose account declaration explicitly accounts for prior conversions and
current cash; never apply the original combined correction a second time.

Proposed authenticated endpoints (names are new, not currently available):

| Operation | Behavior |
| --- | --- |
| `POST /serenity-api/conversions/approvals` with `report_token`, explicit report digest, selected source IDs and account correction cents, backup evidence reference and rollback deadline | Re-verify signature/version/owner, digest and **exact** report body against what the owner saw. Show per-record and correction confirmation in UI, with a cancel/no-op path. Server checks every selected source is eligible and every affected account group is complete, checks backup gate and freshness, then stores immutable approval only; **does not execute**. Return approval ID, digest and state. |
| `POST /serenity-api/conversions/{approval_id}/execute` with an idempotency key and explicit final confirmation | Owner-scoped. Recheck gate and full freshness inside the write transaction. Apply **only** the approved set and exact amounts. Return committed event, before/after totals and IDs. A repeat of the same key for the same approval returns the prior committed result; a different payload/key for an executed approval conflicts. No arbitrary IDs or amounts in execute payload. |
| `GET /serenity-api/conversions/{id}` and owner-private evidence export | Show report hash/version, immutable report, approval and execution state, opening/source links, cash entry, eligibility, rollback deadline, warnings and before/after proof. Exports include raw cents/units, provenance, unknown dates, history and references. Bump the owner JSON export format and verify same-owner referential closure; CSV income/expense behavior stays unchanged. |
| `POST /serenity-api/conversions/{id}/reverse` with a separate authenticated confirmation and reason | Only inside the approved window, if dependency checks pass. Add a linked compensating cash entry and reverse eligibility in one transaction; retain source snapshot, approval, original entries and reversal event. Repeat safely returns existing reversal; otherwise conflict. No automatic database restore. |

Never treat possession of a preview token or approval ID as permission to write:
verify current session, owner and explicit confirmation each time. Foreign report
or IDs return 404; malformed/declaration mismatch 422; stale, previously
executed/conflicting idempotency, or dependent activity 409; missing backup
gate 503/blocked. Responses and downloads use `Cache-Control: no-store`.
Approval and execution are separate user actions, not one combined request.

## Transactional invariants and stale protection

Approval and execution must both use a consistent owner cutoff. The existing
read-only fingerprint is a one-statement capture of current owner rows, but
format 1 does not include future conversion tables; extend/version it before
execution. Canonicalize deterministically (including null dates and raw integer
values). Compare current dependencies to the stored fingerprint, not just
`updated_at` or a net-worth total. Include changes to account balances,
transaction additions/edits/deletions/corrections, source edits/status,
container membership/status and account link, specs/identity/status,
valuation and prior conversion/eligibility/activity. A change anywhere in
the report's owner-wide dependency set invalidates approval; regenerate and
reapprove. Never silently recompute an approved amount. Signing-key rotation
can invalidate unapproved tokens; an already durable approval preserves its
verified report and hash but still requires current freshness and owner checks.
Expire approvals after the configured window; changing backup evidence or
rollback terms requires a new approval.

Serialize financial writes for the same owner with a documented shared write
lock used by **all** account/transaction/investment/container/spec/valuation
writers, not just conversion endpoints. For PostgreSQL, lock a stable owner
workspace row (or a documented transaction-scoped owner advisory key) before
freshness capture and hold through commit; lock/refresh affected children and
parents in stable ID order. Under SQLite, begin an immediate write transaction
before capture so competing writers cannot slip between validation and commit;
enforce FK constraints. If unmediated direct DB writers remain possible, use
serializable transactions with retry-and-recheck or equivalent DB protections,
not a process-local mutex. Lock and refresh the child before inspecting a
mutable container's parent. Never rely on stale ORM identity-map values.

Inside one transaction: claim the approval/key, recapture dependencies and
compare fingerprint, validate ownership, target activity and explicit group
completeness, check backup gate, insert immutable openings/source links, insert
cash correction entries, select replacement eligibility, recompute affected
account balances and owner-wide totals, compare **each component and the delta**
to approved integer cents, append event, mark approval executed, commit.
Any mismatch/overflow/constraint failure rolls the entire transaction back
and returns a conflict; no partial eligibility or cash effect. A unique
owner+source link, unique approval execution and idempotency-key/payload binding
are final DB backstops against duplicate or concurrent requests. Concurrent
distinct approvals for overlapping sources cannot both succeed; the loser
must obtain a new report. Never retry a failed transaction without recapturing
and revalidating its report.

The new cash calculation is `opening_balance_cents + active Income/Expense
transactions signed cents + non-income reconciliation entries signed cents`
(and later actual investment cash activity exactly once). Show the correction
as a separate audited cash reconciliation line, not income, expense, P&L,
dividend, or transfer. For net worth count all existing account balances per
current policy, eligible unmigrated **active** legacy sources, eligible **active**
replacement holdings, minus active debts. Portfolio totals summarize these
components only. A manual valuation after conversion affects the holding
path, never reactivates the legacy value; undated original values are labeled
as such, not as live prices. The report comparison must use the original value,
not a refreshed quote.

## Reversal and dependent activity

Simple reversal is allowed only within the approved deadline, under the same
owner lock and a fresh dependency check, with a verified current snapshot.
The reversal baseline is the committed **post-conversion** event/state, not
the pre-conversion preview fingerprint (which the conversion itself changed).
Allow unrelated financial changes only if they are proven not to depend on the
converted sources/account correction; conservative refusal is preferable to
guessing. Block if any subsequent holding activity, valuation update,
correction/replay, source-mapping change, account transaction or balance edit
depending on the corrected cash, later conversion sharing that account,
portfolio/account relink, or downstream fact using the opening position exists.
Record the blocking IDs privately for the owner. In particular, do not remove
cash used by later spending or erase later activity with a backup restore.
When safe, assert current converted state and balance exactly match the
reversal preconditions; append compensating entry, restore legacy eligibility
and writable original state, mark opening reversed, recalculate expected
component totals, append reversal evidence and commit atomically. Historical
source content must still match its snapshot; do not delete it or original
approval. Subsequent conversion would need a separately reviewed policy; the
unique source link prevents accidental reuse. After deadline or dependent
activity, stop and require a **separately approved corrective plan**; do not
provide a forced reverse button. Rehearse reversal only on disposable data.

## Acceptance proof before enabling real execution

- Fresh and seeded two-owner additive upgrades leave preexisting rows,
  formulas and exports unchanged; populated downgrade refuses. Startup and
  publish perform no conversion. Cross-owner IDs, reports, correction requests,
  evidence reads and exports reveal nothing; DB owner FK constraints reject
  mixed-owner rows.
- On synthetic fixtures, clean `$2,000 cash + $8,000 legacy` stays `$10,000`
  after conversion, while combined `$10,000 account + $8,000 legacy` becomes
  `$2,000 cash + $8,000 holding = $10,000` with an approved `-$8,000`
  **non-income** entry and `-$8,000` net-worth delta. Check every component
  in cents and no income/expense, purchase, or fabricated acquisition date.
- Mixed/unknown/partial groups, zero or unknown basis, inactive sources,
  ambiguous exact specs, unknown beneficial ownership, mismatched evidence,
  undated values and stale prices block or remain flagged exactly as reported.
  Repeated or concurrent execution, crash before commit and injected failure
  between writes leave one complete conversion or none.
- Changes to any fingerprinted dependency between preview/approval/execute
  reject the report; owner-wide serializing tests on disposable PostgreSQL
  and SQLite cover competing writes and stale ORM reads. Demonstrate exact
  retry behavior, read-only protection of converted originals, disjoint
  valuation selection in every summary, and correction-aware cash reads.
- Safe reversal restores eligibility/cash once without removing history;
  every dependent-activity case blocks it, including later account changes
  and shared-account conversions. Exports retain report, approval, snapshot,
  pinned spec, cash correction, eligibility and reversal references. Test
  recovery of the **new schema** with the separate backup workstream in an
  isolated destination; no live-data rehearsal in this task.

None of these proofs has been run by this design document. Real-data review,
backup confirmation, implementation authorization, conversion authorization,
publication and GitHub synchronization are independent decisions.