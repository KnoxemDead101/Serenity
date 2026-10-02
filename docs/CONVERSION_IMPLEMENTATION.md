# Reviewed investment conversion: implementation boundary

Implementation was authorized separately from real-data execution. This slice
does not authorize a real conversion, publication, or GitHub synchronization.
The approved design and Phase 2 scope remain normative.

## Review and execution

- Format 1 previews remain disposable, read-only evidence.
- `POST /serenity-api/reconciliation/execution-preview` creates a signed format
  2 report using algorithm `conversion-execution-2`. It captures all currently
  supported owner dependencies under the financial write lock.
- `POST /serenity-api/conversions/approvals` stores the exact reviewed report,
  digest, complete eligible source set, corrections and rollback terms. It
  does not execute.
- Execution is a separate confirmed request to
  `POST /serenity-api/conversions/{approval_id}/execute`. The idempotency key
  binds the exact confirmation payload. A matching retry returns the committed
  event; a conflicting key or overlapping stale approval cannot apply twice.
- Owner-private evidence is available at
  `GET /serenity-api/conversions/{approval_id}`, `/evidence`, and `/export`.
  Success and error responses for conversion and reconciliation use `no-store`.
- Reversal is a separately confirmed request to
  `POST /serenity-api/conversions/{approval_id}/reverse`. It compares a fresh
  snapshot to the committed post-conversion baseline and recomputes every
  component before and after. Changed dependencies or later conversion events
  block reversal, with owner-private blocking references in the error.

Unresolved and inactive sources are never silently converted. Original typed
values retain their provenance and unknown acquisition dates; they are not
quotes, trading transactions, or verified tax basis.

## A later batch on the same account

`GET /serenity-api/conversions/review-context` returns only the current owner's
prior account/source, opening and cash-entry references. It is review context,
not authorization. The review UI displays these references without selecting
or approving the attestation for the owner.

Account evidence must enumerate all new and prior sources, plus the exact
`prior_opening_position_ids` and `prior_cash_entry_ids`, and explicitly set
`prior_conversion_complete=true`. Omissions, duplicates, foreign references,
unresolved members, and reversed prior sources block the affected group.

Previously converted securities are already separate holdings. Cash-only
evidence reconciles current cash exactly. Combined evidence reconciles current
corrected ledger cash plus only newly represented legacy security values.
Only those new values receive a new non-income correction. A prior correction
must never be subtracted again.

Converted originals are read-only in the API, UI and migrated database. After
safe reversal they can be edited as legacy sources, but cannot be deleted or
converted again; their original opening snapshots and audit links remain.
Account balances show a separate audited non-income cash reconciliation line.
JSON export format 7 retains raw units/cents, Goal/composition records and all
conversion evidence.

Incoming portfolio-first drafts remain uncounted before review. Format 1 keeps
its direct portfolio/account mapping semantics. Format 2 additionally requires
an explicitly selected existing account link pinned to that same portfolio and
Account; entry does not infer or create it. A reviewed pending draft contributes
zero current legacy value and its original entered value to the proposed
opening. The exact resulting delta is approved (including any evidence-backed
combined-balance correction), not assumed to be zero. Reversal returns the
original pending/uncounted state without rewriting the source.

## Schema and concurrency

Revision `0016_approved_conversions` creates the empty ledger and owner-matched
constraints without converting rows. Revision `0017_conversion_guards` adds
database write/lifecycle guards. It also corrects an earlier, empty development
prototype's textual delta column to BIGINT. That correction refuses any
conversion history rather than rewriting audit evidence. Fresh installs already
have a BIGINT delta. Revision `0020_conversion_integration` merges the existing
conversion and Goal/draft revision branches without rewriting their histories.
It also brings Goal/composition writers into PostgreSQL owner serialization.
Those records are freshness and reversal dependencies, not live portfolio-fed
Goal progress. Downgrades refuse conversion history.

Services serialize owner-scoped financial writes before freshness checks.
PostgreSQL database triggers make direct SQL writers join the same advisory
lock, including fingerprinted setup records; SQLite uses an immediate
transaction. Multi-statement dashboard and JSON evidence reads observe cash
and selected holdings on the same side of a conversion commit.

Future activity or valuation records must join the dependency snapshot, shared
write protocol, selected valuation readers, exports and reversal blockers
before being enabled for converted sources. This implementation does not
claim to verify a separate activity slice absent from this workspace.

## Backup coordination and proof

The production gate is deliberately blocked with HTTP 503 until the separate
off-host backup workstream supplies trusted verification. A user-entered
reference, an owner JSON export, or a passing local restore is not verification.
See [BACKUP_RESTORE.md](BACKUP_RESTORE.md) for the existing recovery boundary.
That workstream must cover the intended database/host/version, schema revision,
recent native backup, off-host encryption, recoverable restricted keys,
successful isolated restore, pre-conversion cutoff and writer-quiescence policy.
It must bind verified evidence to the exact reviewed state and agreed rollback
window before replacing the fail-closed gate. Backups are not rebuilt here.

Only explicitly gated disposable tests bypass the unavailable production gate.
The tests prove synthetic two-owner SQLite and PostgreSQL conversion,
concurrent same-key and overlapping execution, stale ORM refresh, exact totals,
atomic failure rollback, immutable migrated evidence, owner isolation and
safe compensating reversal. Native SQLite and PostgreSQL rehearsals include
all new ledger tables and compare restored owner-private evidence.

Run `bash scripts/prepublish_check.sh` for the full isolated PostgreSQL/browser
suite. A future publication still requires separate permission, published
sign-in verification and real off-host backup readiness.