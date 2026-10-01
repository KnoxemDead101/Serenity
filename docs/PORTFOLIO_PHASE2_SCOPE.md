# Profit Engine Phase 2: approved design boundaries

## Status and authority

On September 29, 2026, the owner approved the proposed Phase 2 design without
amendments. This is **design approval only**, not implementation, real-data
conversion, deletion, source push, or publication authorization. No application
behavior or financial records were changed by this scoping work.

Subsequently the owner authorized **only delivery-sequence step 1** to begin:
private named portfolios and investment-account metadata linked to existing
Accounts, with APIs, UI, export and isolation tests. This authorization does
not approve opening-position conversion, reconciliation cash corrections,
investment activity, a net-worth switch, production deployment or GitHub
synchronization.
Implementation and verification must be distinguished from the original design
approval and from eventual production publication.

The owner subsequently requested that newly entered Investments choose an active
portfolio/container and remain **uncounted drafts until account review**.
The owner then clarified that a portfolio should hold investments directly;
new investments require only an active portfolio, not an existing Account or
container. The Finances form saves direct portfolio membership and opens the
read-only review on Portfolios. Account selection happens during review, not
at investment entry. Existing account/container links remain stored for
historical review; the normal portfolio page hides their management unless
one already exists. This does not approve conversion, certify the account's cash
meaning, or turn a preview into executable approval. Existing unassigned
Investments retain their prior treatment. They may be manually placed in an
active portfolio as organization-only metadata without changing their counted
status. No existing investment is automatically assigned or converted.
Archived or foreign containers cannot
receive a new draft. A reviewed draft can have a nonzero proposed delta when
the linked account is cash-only; combined balances require exact cash evidence
and an offsetting correction. Do not apply legacy zero-delta assumptions to it.

When asked what existing brokerage/retirement/trading balances represent, the
owner selected “Mixed, unsure, or no existing records” without clarification.
Therefore existing balances are **unreconciled**. Do not infer either cash-only
balances or an empty database. No real records were inspected for this scope.
Account-by-account facts must be established before any valuation switch.

This document resolves Phase 2 policy questions in PROFIT_ENGINE_REVIEW.md.
That review remains the broader roadmap; later trading decisions remain open.

## 1. Responsibilities and relationships

- Persist multiple workspace-private named Portfolios, including empty ones.
  A child-labeled portfolio is organizational only, not shared access or proof
  that its assets legally belong in the user's net worth.
- Add InvestmentAccount metadata as a container with one Portfolio membership
  and one unique, owner-checked link to an existing Account cash ledger.
  An Account cannot back multiple containers. No second cash balance is stored.
  Accounts outside portfolios continue to work normally.
- For the organization-only first slice, the Account link is immutable after
  creation; portfolio membership can be edited to regroup the container.
  Archived containers continue to reserve their linked Account. Archiving a
  portfolio with active containers must be refused rather than cascading; move
  or archive those containers first. Archive does not remove financial value.
- Account is the cash ledger; securities quantities, basis and valuations belong
  to opening snapshots and subsequent activity/derived holdings, not Account.
  Membership changes regroup assets, not move money or create income.
- Every new row carries workspace ownership. Resolve workspace from verified
  authentication, never from a client-selected owner. Validate portfolio,
  account, instrument and exact specification together under that owner.
  Use matching owner+ID composite constraints for new relationships where
  practical, alongside service checks; existing single-column FKs are not
  sufficient ownership protection.
- Reuse reference instruments and immutable specification versions. Pin the
  verified exact spec; never match on ticker alone, rewrite an old spec, or
  treat the hypothetical calculator as activity or a price feed.

After approved reconciliation, the target formula is:

    net worth = cash counted once
              + eligible unmigrated legacy investment values
              + eligible replacement/new holding values
              - debt balances

Portfolio totals are summaries, not another term in this formula. Legacy and
replacement representations of the same asset are mutually exclusive.
Personally owned real assets alone qualify; simulation and prop buying power
do not. Beneficial ownership/inclusion must be confirmed in reconciliation,
not inferred from a portfolio name.

Until reconciliation and switch approval, current formulas and records remain
unchanged. Shadow calculations must clearly disclose unresolved overlaps, not
silently claim a corrected total. Do not turn all existing account balances into
cash by renaming their labels.

## 2. Opening positions and approved conversion boundary

Default: leave existing Investments unchanged. Conversion is optional and
requires an explicit per-owner, per-record approved reconciliation report.

For each candidate, capture original ID, owner, active status, name, ticker,
quantity units, entered basis cents, entered value cents, notes and timestamps.
Preserve an immutable source snapshot and reversible conversion linkage.
Resolve the target container, cash account, verified instrument and spec
explicitly. Missing or ambiguous instrument identity blocks that conversion.

The target is an **opening-position snapshot**, not BUY activity. Do not invent
acquisition dates, prices, dividends, tax lots, cash outflows or historical P&L.
Separate capture time, record-edit time and actual valuation as-of time.
Unknown acquisition/valuation dates remain unknown, not filled from updated_at.
Original typed value can be retained as an undated legacy valuation with a
visible provenance warning; it is not a current market quote.

Preserve entered basis as user-entered/unverified unless evidence verifies it.
Unknown basis stays unknown, with dependent gains unavailable; a legacy zero
must be reviewed rather than presumed either verified zero or missing data.
Inactive sources stay excluded unless separately approved for reactivation.

Converted originals are retained as read-only historical sources; they must
not remain an independently editable/countable asset. This protection begins
only with the approved conversion, not as an automatic change to legacy CRUD.
No conversion approval authorizes original deletion. Posted future activity
uses corrections/reversals rather than destructive edits/deletes.

### Conversion execution requirements (future implementation)

1. Add empty schema separately from conversion. Schema upgrade/startup/publish
   must never perform implicit backfills, instrument guesses or valuation
   switches. Preserve legacy CRUD until a record is explicitly converted.
2. Generate a dry-run report under one owner and consistent cutoff. Include
   every affected source/target, basis status, valuation provenance, confirmed
   cash-versus-combined account meaning, inclusion decision, overlap correction,
   current total, proposed total and explained delta.
3. Keep unresolved records out of the conversion batch. They retain their
   existing treatment, clearly flagged; an unresolved account cannot be
   declared cash-only. New assets must not be counted over unresolved combined
   balances for that same account.
4. Obtain approval for the exact report and any cash/overlap correction. Reject
   stale approval if source balances, transactions, positions, membership or
   valuations changed. No fake income/expense transaction to correct overlap.
   The audited non-income cash-reconciliation mechanism must be implemented
   and tested before an affected account can switch.
5. Require a usable backup and agreed rollback window before real conversion.
   Atomically store approved snapshots/linkage, cash correction if any, and
   mutually exclusive valuation eligibility. Uniqueness/idempotency must
   prevent retries or concurrent approvals from converting a source twice.
6. Compare actual results to the approved report exactly in integer cents.
   Preserve approval, report version and before/after evidence. No switch on
   unexplained mismatch.
7. Rehearse rollback in isolation. A simple rollback is allowed only if no
   dependent activity has been posted. Otherwise stop and require a separately
   approved corrective plan; never erase later activity by restoring old state.
   Deletion, push and publication remain separate authorizations.

The separately authorized execution slice is specified in
[APPROVED_CONVERSION_DESIGN.md](APPROVED_CONVERSION_DESIGN.md). That design does
not itself authorize implementation or conversion.

## 3. Future activity and cost policy

Approved initial holdings scope is USD, long stocks/ETFs with manually entered,
dated, attributable valuations. Unknown/stale valuations are disclosed; no
automatic pricing is implied. Futures reference math remains available but
futures holdings accounting is not included.

Use moving weighted-average cost for **performance reporting, not tax lots**.
Purchase fees increase basis; sale fees reduce proceeds. Preserve exact scaled
quantities and integer cents, using Decimal/integer intermediates, never float.
Future implementation must specify deterministic ordering, partial-sale
rounding/residual allocation and correction replay, and prove that closing the
position releases all remaining basis. Unknown opening basis propagates to
dependent gain calculations rather than becoming zero.

Record actual BUY/SELL/DIVIDEND activity, pinned specifications, dates, quantities,
prices and fees. BUY reduces cash, SELL increases cash by net proceeds, and a
received cash dividend increases cash exactly once. Do not count activity
proceeds or realized gains a second time as assets. Opening positions never
post cash. Linked cash and holding effects must commit or fail together.
The existing income/expense-only transaction system is not sufficient evidence
that these semantics already exist.

Posted facts are retained; corrections reference and reverse/supersede prior
facts with an auditable recomputation. Reject oversells and invalid activity.
Archive containers with history rather than cascading deletion; archive must
not silently remove assets from valuation.

Out of scope: atomic inter-account transfers (separate slice), futures
accounting, margin, shorts, tax lots, multicurrency, broker feeds, automatic
trading and corporate actions. Reinvestment must not be fabricated from a
cash dividend. Realized R and advanced trade-plan policies remain undecided.

## 4. Synthetic before/after reconciliation

All examples below are invented USD fixtures, not actual user balances.
Unrelated cash/debts are held constant at zero for clarity.

| Net-worth component | Clean before | Clean after | Overlap before | Overlap after |
| --- | ---: | ---: | ---: | ---: |
| Account balance counted | $2,000 | $2,000 | $10,000 | $2,000 |
| Legacy security counted | $8,000 | $0 | $8,000 | $0 |
| Replacement holding counted | $0 | $8,000 | $0 | $8,000 |
| Total | **$10,000** | **$10,000** | **$18,000** | **$10,000** |
| Approved delta | | **$0** | | **−$8,000** |

For both examples, suppose the source has 40 shares, entered basis $6,000 and
entered value $8,000. The opening snapshot preserves all three, with basis
unverified and valuation date unknown unless supplied. It does not create a
40-share historical purchase or a $6,000 cash deduction. In the overlap case,
evidence must establish that the original $10,000 was $2,000 cash plus these
$8,000 securities. The $8,000 reduction corrects duplicate counting; it is
neither an investment loss nor a zero-delta migration.

An inactive source remains zero in both totals. An unresolved source remains
unconverted. A mixed batch must report each outcome and cannot hide an overlap
correction behind unrelated gains or refreshed prices.

## 5. Isolated verification plan and release gates

These are release requirements, **not evidence that tests have run or that any
production data has been inspected**. Verify each implemented slice using
synthetic temporary SQLite and disposable PostgreSQL, never the live DB.

| Area | Required proof |
| --- | --- |
| Additive migrations | Fresh upgrade; upgrade seeded legacy/two-owner data; unchanged balances, source fields and existing exports; empty-schema downgrade; refuse destructive downgrade when new records exist. |
| Relationships | Empty/multiple portfolios; one container membership and unique cash link; regrouping leaves net worth unchanged; cross-owner parent/spec combinations fail at services and new DB constraints. |
| Ownership | Two authenticated owners; foreign IDs on create/read/edit/archive/convert/correct rejected as not-found; owner spoofing, bulk/pagination, summaries, preview reports and exports cannot leak another owner's records; failed writes leave no partial rows. |
| Reconciliation | Both numeric examples above; mixed/unknown balances; inactive/zero/unknown-basis sources; no records; ambiguous tickers/specs; partial batches; no legacy+replacement double count; price updates cannot mask conversion delta. |
| Atomicity | Duplicate requests, concurrent conversions, stale report approval, failures between cash/holding writes and retries are all safe; unique source linkage; exact cents conservation; no startup/publish conversion. |
| Activity | Fractional quantity/overflow limits, purchase and sale fees, deterministic partial exits, final basis residual, dividends once, oversell rejection, unknown basis propagation, correction replay and pinned archived specs. |
| Rollback | Restore originals and valuation eligibility together within approved window; block simple rollback once subsequent activity exists; preserve later history and require reviewed corrective path. |
| Exports | Version the JSON shape; retain source snapshots/status, conversion IDs, portfolio/account links, all pinned specs, activity/corrections, raw units, basis status, valuation source/as-of/capture times and reconciliation/approval evidence; every included relationship resolves within the same owner. |
| UI | Explicit cash vs holdings labels, dry-run delta, unresolved warnings, per-record confirmation, cancellation/no-op, stale approval errors, source read-only state and no implied tax/price-feed claims. |

Export tests compare exact units and relationships with seeded expected data,
including retained inactive/converted sources and corrected activity. Maintain
existing transaction CSV behavior and injection protection. JSON export is
not an import/restore guarantee; native backup recovery remains separate.

Before a future publication, run the project's full prepublish gate in
addition to these tests. Published sign-in and off-host recovery are existing
separate workstreams, not certified here.

## 6. Delivery sequence

1. Authorized to begin: build private named portfolios and uniquely linked
   investment containers, APIs/UI/exports and isolation tests; no conversion
   or dashboard changes. Migration `0015_portfolio_containers` is additive:
   new tables and an Account `(owner_id, id)` unique index for composite
   owner-matched foreign keys, without rebuilding Accounts, modifying legacy
   Investments or altering amounts. Owner-scoped JSON export format 3 adds
   both metadata tables; transaction CSV retains its existing behavior. This
   is not approval to migrate production or publish.
2. Build opening snapshots and owner-reviewed reconciliation workflow with
   synthetic migration/rollback proof. Real execution remains separately gated.
3. Build weighted-average stock/ETF activity with atomic cash effects and
   correction history; validate detailed rounding and ordering before enabling.

Relevant existing foundation: models/account.py, models/investment.py,
models/instrument.py, services/account_service.py, services/finance_service.py,
services/dashboard_service.py, services/instrument_service.py and
services/export_service.py. The design document itself implements none of these
features; check current code and verification before claiming a slice is shipped.