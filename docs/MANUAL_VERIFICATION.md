# Explicit owner checks of manual financial facts

## Reviewed design and meaning

On **2026-10-02**, before implementation, the owner approved: latest owner-only
evidence per source, explicit as-of date/scope/evidence, binding to the displayed
financial snapshot, retention until replacement or deletion, and no financial
amount or operational-permission changes.

Supported scopes are an active account's **derived current balance**, an active
debt's **entered balance**, an eligible legacy investment's **entered valuation**,
and a selected opening's **original entered valuation**. A valuation check does
not establish cost basis, real trades or realized profit. These owner assertions
are not independent bank/broker verification, completeness certification, live
quotes, conversion approval or permission to write financial records.

Each check requires a deliberate **as-of date of the checked fact** and nonblank
evidence reference/explanation (maximum 1,000 characters). The browser does not
default a date and requires confirmation that the owner checked the displayed
snapshot. The server records a separate UTC recording time. Do not include
credentials, account numbers or full statements in evidence. There are no
uploads, external fetches or credential requests.

## Dates and reminders

| Review status | Meaning |
| --- | --- |
| UNKNOWN | No explicit check exists, even for a newly edited input or zero amount. |
| VERIFIED | The current fact matches explicit dated owner evidence, less than 30 UTC calendar days old. Still manual, not independently verified. |
| STALE | Matching evidence is at least 30 UTC calendar days old; a review reminder, not proof of an incorrect value. |
| CHANGED | Saved evidence does not match the current financial snapshot and cannot verify it. |
| INCONSISTENT | Persisted evidence failed validation (including future dates/times). Never presented as a verified fact. |

Dates and explanations have no defaults. Missing/malformed/future dates and
missing/blank evidence are rejected at the API boundary. Persisted evidence is
revalidated before it can establish a match. SQLite naive stored timestamps are
interpreted as UTC. Recording a check does not update a financial edit timestamp.
Editing notes never creates, refreshes or resets a check.

Data Health summary findings remain redacted. Matching checks supersede their
own source's last-edit age or opening valuation age/missing reminders, not those
of other unchecked sources. Existing source validation still runs; explicit
checks never override corrupt conversion evidence. Retained source edits and
conversion capture times still do not establish valuation freshness. Original
conversion as-of evidence and capture timestamps are never modified.

## Snapshot binding and concurrency

A server SHA-256 comparison token binds owner, scope, ID, source generation
timestamp and the reviewed fact/identity. Account amounts use the existing
transaction/cash-correction balance service, not a new formula. Valuations bind
quantity and instrument/container identity; opening valuations also bind
approval and specification. Names, notes and edit timestamps are excluded.
Amounts are server-formatted strings; JavaScript performs no finance arithmetic.
The token is neither a secret nor an authorization credential.

Save compares the submitted token to a fresh authorized source read; mismatches
return 409 and require reloading/rechecking. Subsequent changes show CHANGED.
Source ID reuse cannot inherit verification because generation differs. Returning
to precisely the same fact and identity within the same generation restores a
match: this is a fact snapshot, not a complete change history.

These are momentary observations, not serializable reconciliation certificates.
A concurrent financial change after a read is detected by the next observation.
No new financial locks/write controller are added. Concurrent first inserts
conflict safely under a unique target key. Existing check replacement is
last-committed-write-wins; there is no immutable check history.

## Ownership, retention and deletion

The verified session supplies the owner, never the browser/request. All source
resolution and evidence list/save/delete operations are owner-filtered. Foreign
and missing records both return 404. Unknown fields, including owner and amount,
are rejected. Evidence text is restricted to the authorized review API/UI; it
does not enter aggregate findings, operational history or application logs.
System responses, including authentication/validation/conflict failures, are
`Cache-Control: no-store`.

`manual_verifications` stores only the latest check per owner/scope/source.
Replacement removes the prior check from this live table. Explicit deletion
removes the check and restores UNKNOWN. Inactive, deleted or deselected sources
leave owner-only evidence in a separately removable **retained evidence** list;
it does not verify a current financial fact. Polymorphic references deliberately
have no financial-table FK/cascade, so evidence does not change source deletion
or conversion behavior. Services check owner, source generation and selection.

There is **no automatic expiry**. Thirty days is a reminder, not deletion
retention. Removal from the live table does not promise erasure from backups or
database recovery history; those policies remain separate. Downgrade refuses to
drop nonempty evidence. The additive migration changes no financial rows;
production startup must never migrate.

## API and interface

- `GET /serenity-api/system/verifications`: current targets (scope, label,
  server-formatted amount, snapshot token, saved check, status), separately
  retained evidence and UTC checked time.
- `PUT /serenity-api/system/verifications/{kind}/{target_id}`: required
  `as_of`, `evidence`, `snapshot`, with no caller-selected amount/owner.
- `DELETE /serenity-api/system/verifications/{evidence_id}`: owner-only removal.

The plain-HTML System review section is separate from the redacted health
summary. It supports save, replacement, deletion, and retained-evidence removal.
Dates/evidence/confirmation must be explicit. Failed refresh and expired/inactive
sessions clear private evidence; stale request responses cannot restore it.
All returned text uses text rendering, never HTML interpretation.

Unreadable review data returns 503, not fabricated empty results. The optional
evidence table does not change runtime System state; Data Health reports affected
domains as unavailable if it cannot read evidence. Existing financial write
safety still applies to evidence mutations, without a bypass or permission change.
Live feeds, backups, status history, conversion execution/audit, structured
Goal/Project reviews and published sign-in remain separate.

## Verification

Synthetic SQLite/PostgreSQL and real plain-HTML Chromium tests cover missing and
future dates, explicit zero, note edits, snapshot changes, 30-day boundaries,
owner isolation, retention/deletion, source generations/selection, validation
failures, no financial mutations and additive migration preservation.

Run `bash scripts/prepublish_check.sh` for the full required disposable
PostgreSQL/Chromium gate. Public preview screenshots show sign-in only;
authenticated controls are verified by disposable authorized browser fixtures,
not the published signed-in UI.

Full required gate on **2026-10-02**: **1,166 passed, 2 skipped**, exit 0,
with two existing dependency deprecation warnings. Required disposable
PostgreSQL and Chromium checks ran. No existing database was migrated by the
gate; only the development preview applied the additive evidence migration.