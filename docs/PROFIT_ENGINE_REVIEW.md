# Profit Engine: repository review and incremental design

**Phase 2 design update (September 29, 2026):** The owner approved the boundaries
in [PORTFOLIO_PHASE2_SCOPE.md](PORTFOLIO_PHASE2_SCOPE.md): private portfolios,
one linked cash ledger per container, reconciled opening snapshots and
performance-only moving weighted-average stock/ETF activity. Existing balances
remain unreconciled. This supersedes the approval status of the Phase 2
recommendations below, not their implementation status. The owner subsequently
authorized **only Phase 2a organization** (private named portfolios and
investment-account containers linked to existing Accounts) to begin. No
conversion, cash correction, legacy deletion, source push or publication was
authorized; each actual conversion still requires an approved report.

This review responds to the September 29 architecture handoff. It distinguishes
the **implemented and locally tested Phase 1 instrument/calculator slice**, the
organization-only Phase 2a work and future recommendations; local tests do not
certify publication, production sign-in or production recovery. Portfolio
conversion, transfers, trading
records and dashboard integration require separate decisions and tests. No
existing user records are transformed by this slice.

**Implemented Phase 1 scope:** `models/instrument.py`
defines an owner-private, immutable-symbol `Instrument` with archive/reactivate
instead of deletion and append-only `InstrumentSpecification` versions. A spec
stores name, asset type, exchange, USD currency, tick size and point value as
BIGINT 1e-8 units. `migrations/versions/0014_instrument_registry.py` adds
tables without rewriting investments. `schemas/instrument.py`,
`services/instrument_service.py` and `api/instruments.py` define private CRUD;
`schemas/trading_math.py` and `services/trading_math.py` support a hypothetical
calculator at `/serenity-api/profit-engine/calculate`, not posting trades.
`frontend/profit_engine.html` and `frontend/static/js/profit_engine.js` expose
the `/profit-engine` page. `services/export_service.py` originally included
both reference tables and every spec version in JSON format 2; format 3 adds
Phase 2a metadata. These are **development code changes**,
not a claim that the production app has been published or production sign-in
verified. There are no seeded instruments, live prices, actual fills,
positions or net-worth changes in this scope. Isolated migration, ownership,
arithmetic, export and browser tests exercise the slice; run the full
prepublish gate again before publishing.

## A. Current repository assessment

- `models/account.py`, `models/transaction.py`, and
  `services/account_service.py` calculate account balances from an opening
  balance and signed, nondeleted income/expense transactions. Account types
  already include Brokerage, Retirement and Trading (`utils/choices.py`), but
  `schemas/transaction.py`/`services/transaction_service.py` do not provide an
  atomic transfer type. A category named Investment Contribution is **not** a
  transfer.
- `models/investment.py`, `schemas/finance.py`, `services/finance_service.py`
  and `api/finance.py` implement a temporary manually valued investment:
  ticker is optional, quantity uses signed BIGINT units of 1e-8, and cost basis
  and current value are entered in cents. Legacy investments have no link to
  the new instrument registry, holdings ledger, activity history or price feed.
  Active investment value contributes
  to `services/dashboard_service.py` net worth alongside account balances and
  minus active debt. This creates a double-counting risk if brokerage account
  balances already include the same holdings.
- Bills, debts and investments now have **confirmed permanent deletion**,
  including previously inactive records (`api/finance.py`,
  `frontend/static/js/finances.js`). The handoff's earlier statement that all
  financial history is retained is out of date. Account deactivation and
  transaction/correction history have different protection. Deleted finance
  rows are absent from later JSON exports; earlier database backups can still
  contain them. `services/export_service.py` exports owned records to JSON and
  transactions to CSV; that JSON is not a verified import/restore format.
- `models/identity.py`, `services/identity_service.py`, `auth.py`, and
  `services/ownership.py` map a verified Clerk identity to one internal
  workspace ID. Existing financial routes depend on `require_session`;
  service list/get methods filter `owner_id`. Most financial tables store
  workspace ownership as a string, not a foreign key to `workspaces`.
- `utils/money.py` owns exact Decimal/integer conversions, including cents,
  milli-percent and 1e-8 quantities. `schemas/finance.py` limits investment
  quantity to 1,000,000,000. `migrations/versions/0012_*` widens investment
  quantity to BIGINT, and `0013_*` widens cent columns. `main.py` wires thin
  API routes and serves plain `frontend/` HTML/CSS/JS; migrations are explicit.
  The current responsive interface has separate finance and dashboard pages.
  Tests cover SQLite, owner isolation, browser behavior and disposable real
  PostgreSQL (`tests/test_money_postgres.py`, `tests/test_migrations.py`).
- The Phase 1 files named above add **reference metadata and hypothetical
  calculations only**. Investment records, holdings accounting, posted
  transfers, trade execution history and current dashboard valuation are
  still separate/unimplemented.

## B. Existing architecture to reuse

Keep the current account/transaction/correction, bill/debt, investment and
dashboard services intact while adding new domains. Use `require_session`,
owner-scoped service queries, Pydantic Decimal validation, integer cent/quantity
helpers, explicit Alembic migrations, and the existing `api/` → `services/` →
`models/` pattern. Reuse the current SQLAlchemy session and plain frontend
conventions rather than adding a framework. Add domain-specific helpers to
`utils/` or `services/` only when there is an actual calculation to centralize.

## C. Conflicts, debt and loose ends

1. Existing Brokerage/Retirement/Trading account labels do not distinguish
   cash from market value; adding holding values to the current net-worth
   formula without an explicit valuation policy would double count assets.
2. Current income/expense transactions cannot express a balanced inter-account
   transfer. A contribution must not be modeled as income on one side and
   expense on the other.
3. The temporary investment has no acquisition, sale, dividend, instrument or
   as-of valuation facts. Entered cost basis does not prove trade history.
4. Production login/read-write/refresh/sign-out and post-sign-out denial still
   need real published verification. Native backup/restore rehearsals in
   `docs/BACKUP_RESTORE.md` are synthetic; automated encrypted off-host
   backups, recovery objectives and a real-host restore remain operational work.
   Profile settings, invitation policy and safe PIN quick unlock are separate
   unfinished work; do not weaken Clerk to build trading features.
5. Existing finance hard deletion means future holdings/trades need an explicit
   audit/deletion policy before adopting one. No automatic import, live pricing,
   broker integration or notification delivery exists.
6. **Deliberate Phase 1 design:** parent `Instrument.symbol` is immutable and
   `asset_type` resides in immutable specification versions; service validation
   prevents changing type across versions. Duplicating type on the parent is
   unnecessary and would create a second mutable fact to reconcile. Versions
   are append-only via service APIs; there is no SQL trigger preventing a
   privileged direct database edit. All application paths should append new
   versions rather than update existing ones. Archived instruments and their
   specs remain available to the hypothetical calculator by spec ID so future
   historical calculations can be reproduced; archiving only hides them from
   active choices.

## D. Existing investment migration recommendation

**Leave `investments` and its CRUD, exports and dashboard formula unchanged
through Phase 2a.** Do not relabel a snapshot as a buy or infer a historical
price from its current value. In a later separately approved migration, capture
each legacy record and its original ID, owner, status, entered quantity, cost
basis and valuation timestamp/availability. Offer either an explicitly labeled
opening-position snapshot in an owned portfolio/account or keep it read-only
alongside the new ledger until the user reconciles it. Map an optional ticker
only after verifying identity; missing/ambiguous tickers need manual resolution.
Use a tested reconciliation report per owner and parallel-run both valuations
before changing the dashboard; never count legacy and replacement values at
once. Preserve originals and reversible linkage through a rollback window;
conversion and legacy deletion require separate approval and backup.

## E. Proposed domain model

Suggested staged relationships (not a migration mandate):

```text
Workspace ─┬─ Instrument ─ InstrumentSpecVersion
           ├─ Portfolio ─ InvestmentAccount ─ Activity ─ derived Holding
           ├─ TradingAccount ─ TradingDay ─ Plan / Trade ─ Fill
           ├─ MarketAnalysis ─ AnalysisRevision
           └─ MarketArea (level or zone; independent of TradingDay)
```

Persist an owned `Portfolio` because the user wants multiple named groupings
including children's holdings; enforce owned, nonempty names and explicit
membership. An investment account is a container inside a portfolio, not a
second representation of the current account's cash. Persist activity facts
and opening snapshots; derive holding quantity, cost basis and value using
versioned methods. Treat cash movement separately. Persist a TradingAccount
type (`PERSONAL_FUNDED`, `PROP_FIRM`, `SIMULATION`): only personally owned real
assets can enter net worth; prop buying power and simulation never do.
Persist trades and ordered fills, derive open quantity/status. Reviews and daily
journals refer to their contexts rather than becoming unstructured columns.
Use owner-scoped lookups for every parent and cross-reference; composite
owner+ID database constraints provide defense in depth for Phase 2a links.
Other planned models remain deferred beyond Phase 2a.

## F. Instrument registry and authoritative trading math

**Current Phase 1 code shape:** one workspace-private `Instrument` parent with
immutable uppercase symbol and per-owner symbol uniqueness; descriptive
name, asset type (`STOCK`, `ETF`, `FUTURE`), exchange and USD-only currency
live on immutable, sequential specification versions. Each version stores
BIGINT-scaled tick size and **point value** (USD per 1.0 price point), not
tick value; tick value = tick size × point value. Mini and micro futures must
be entered as separate reference symbols/specs, never inferred from names.
Archive/reactivate protects references; metadata edits append a spec instead
of overwriting old facts. The current slice does not store effective market
dates, metadata provenance, quantity increment or a broker-verified symbol
registry. **Proposed for future trades:** pin a trade to its exact immutable
spec ID and retain that ID/version in exports; no historical repricing.
Whether symbols need venue/type-qualified identity, effective dates and a
verified source must be resolved before real trade data is entered.

For this slice, integer units at 1e-8 for prices and fractional
share quantities, with bounded positive 64-bit fields and validation **before**
storage and multiplication; futures prices may be signed, contract quantities
are positive whole integers. Money is USD cents initially as an explicit scope limit, not an assertion that
other currencies can safely be converted at 1:1. Reject unsupported currencies
and amounts that cannot be represented or rounded under the stated policy.
Use Python integers and `Decimal` intermediate arithmetic; define one
half-up-to-cent rounding boundary for an aggregate result, never binary float.
The existing 1e-8/one-billion-share quantity validation can be reused for
share activity if checked against worst-case aggregation and BIGINT range.

Use pure service functions, not frontend arithmetic: for example,
`point_difference(direction, entry, exit)`, `ticks(points, spec)`,
`gross_pnl_cents(fills, spec)`, `planned_risk_cents(entry, stop, contracts,
spec)`, `planned_reward_cents(entry, target, contracts, spec)`, and
`net_pnl_cents(gross, fees)`. For a future: points =
`(exit-entry) × direction_sign` (LONG +1, SHORT -1); ticks =
`points / tick_size`; dollars = ticks × (tick_size × point_value) × contracts. Require
execution/plan prices to be on valid tick increments; fees are separate
nonnegative cents, net = gross − fees. Planned risk uses an adverse stop,
planned reward a favorable target, and R:R = planned reward / planned risk,
undefined if risk is zero. Realized R = net realized P&L / **frozen planned
risk** under a policy to confirm for scaled/partially open positions. For
stocks/ETFs, fractional shares × per-share price difference produce USD value.
The existing calculator API shows **hypothetical** results and does not
persist fills, move cash, change net worth or supply market prices.

Multiple entries/exits later require timestamped, deterministically ordered
signed fills with entry/exit role, price, quantity, per-fill fees and pinned
specification. Aggregate weighted-average entry/exit prices from exact
quantity-weighted sums, but do not use a blended exit to pretend an open
position is closed. Running open quantity = entries − exits; reject exit
quantity above available position (and invalid fills) transactionally.
`PLANNED`, `OPEN`, `PARTIALLY_CLOSED`, `CLOSED` are derived from plan/fills,
not independently editable fields. Realized P&L on partially closed positions
needs an approved matching policy (e.g. moving weighted-average cost vs FIFO);
do not quietly choose one with tax/accounting implications. No order model in
v1. Manual test: calculate a one-contract mini and micro move by hand from
their separate specs, then compare service output and opposite SHORT signs.
This demonstrates immutable facts, value objects and pure, testable math.

## G. Portfolio design

**Why persisted Portfolio is next, not a calculated label:** users need
multiple stable, independently named and owned groupings (e.g. long-term and
children's investments), with deliberate account membership, even when a
portfolio currently holds no activity. Neither current `Account` nor legacy
`Investment` stores that identity/membership. Inferring portfolios from an
account's classification or an instrument's ticker would make an empty
portfolio impossible and risk silently moving records when labels change.
Persist a workspace-owned Portfolio and explicit membership; offer a simple
default-selection UX without assuming one global permanent portfolio.

**Historical account-extension discussion (choice superseded by the approved
Phase 2a design below):**
`models/account.py` already stores workspace owner, account type, institution,
classification, opening balance and linked income/expense transactions;
`utils/choices.py` includes Brokerage, Retirement and Trading. This is a good
candidate for the **cash ledger** of an investment container rather than
creating a second independent cash balance. It has no portfolio relationship,
holding units or position activity, and `services/account_service.py` computes
the account balance exclusively from its opening balance and transactions; existing
`services/transaction_service.py` supports no atomic transfer. Therefore do
**not** equate a current brokerage account balance with securities value,
attach holdings to it without verifying its opening-balance semantics, or
promise linked transfers now. Before *adding holdings to net worth*, audit
how users entered brokerage and trading balances. The earlier alternatives
(Account→Portfolio membership versus a separate one-to-one metadata container)
have now been settled in favor of the separate container. Exactly one cash
ledger exists; future asset value must be separately derived.

Persist multiple owned portfolios and memberships, but allow a simple
single-portfolio UX later. **Approved Phase 2a choice:** a separate owned
`InvestmentAccount` is organizational metadata inside exactly one portfolio,
with a unique, owner-checked link to an existing `Account`; the link cannot
be replaced after creation, even if archived. Portfolio membership can be
edited to regroup it without posting money. A portfolio containing active
containers cannot be archived; archived containers keep the account reserved.
No second cash balance exists. The approved eventual valuation policy still
requires reconciliation and a separately approved per-record switch before
adding holding values. Record future BUY/SELL/DIVIDEND as activity facts,
not changes to typed-in current value; show valuation only with an explicitly
dated, attributable price/statement. Weighted-average cost is a proposed
simple basis, not a tax-lot claim. A checking → brokerage → personal trading
move should be one balanced, atomic owned transfer with two cash legs, no
income/expense classification, identical currency and amount, and net-zero
aggregate cash effect. Prop payouts become real cash only when received.
Transfers are a separate tested slice, not a new transaction category.
Manual check: reconcile both accounts and total net worth before/after a
transfer. This demonstrates ledger invariants and separation of cash vs assets.

## H. Trading workflow

Create instrument-specific independent market analyses with immutable
timestamped revisions. Persist a level/zone as an owned market area (kind,
price or lower/upper bound, lifecycle ACTIVE/TESTED/INVALIDATED/ARCHIVED,
review date), not a child of a trading day. Link a day or plan to specific
analyses/revisions and areas through owned association rows. A TradingDay is
owned, account/instrument/date scoped as appropriate and can exist with zero
trades; an explicit no-trade review explains why. A pretrade plan stores
intended entry/stop/target/quantity/rules and pinned spec; later actual fills
and trade review cannot overwrite that plan. Separate structured trade review
from daily journal, linked by day and optionally trade; shared UI concepts
need not mean a premature generic notes engine. Attachments and thinkorswim
integration remain deferred. Manual check: save an analysis, revise it after
planning, and verify the earlier reasoning still appears unchanged. This
demonstrates versioning, temporal provenance and relational ownership.

## I. Attention and timeline

Build a service that selects source-derived dated items: bill due dates,
planned income when recurrence can be safely determined, and later goal
checkpoints, contribution plans, trading days and stale market areas. Each
result carries source type/ID, owner, date and action link; no duplicate
calendar row for an existing bill. Manual reminders alone can be persisted
independently. An area becomes stale under a configurable review interval,
not because an old TradingDay closed; record actual review time. Dashboard
shows bounded Today's Focus/upcoming highlights and summaries; full filtered
history and calendars belong on dedicated pages. No SMS/email/push in v1.
Manual check: update a bill date and see its single timeline entry move.
This demonstrates a read-model projection without a second source of truth.

## J. Isolation and authorization

Every new financial table should carry an immutable workspace ID or be
reachable only through a strictly owner-scoped parent. Require auth on every
route; resolve instrument, version, portfolio, account, area, plan and fill
against that same workspace *before* referencing them, and return not-found
for other owners. Do not accept client-supplied owner IDs. Foreign keys alone
do not stop foreign-workspace references: validate combinations in services
and, where practical, enforce matching owner IDs with composite unique/FK
constraints. Apply scope independently to dashboard, exports, pagination and
bulk operations. Test distinct authenticated owners on each create/read/edit/
delete and every relationship; invitation never grants access to another
workspace. Manual check: cross-owner IDs must return not-found and leave rows
unchanged. This demonstrates defense in depth.

## K. Exports and recoverability

The owner-filtered JSON export for the Phase 2a slice sets `format_version: 3`
and includes `instruments`, `instrument_specifications`, `portfolios` and
`investment_accounts` with owner-scoped IDs, status, timestamps and raw
relationships (`services/export_service.py`). No source snapshots, holdings,
activity or trading history exists in this slice. JSON export remains an
export, **not** a restorable workspace backup until an importer with
schema-version validation, ID remapping, consistency checks and isolated
round-trip tests exists. Add
human-readable portfolio/trade CSV later, with spreadsheet injection
protection as in `services/export_service.py`. Native encrypted off-host
database backup with rehearsed restore remains the operational recovery
mechanism (`docs/BACKUP_RESTORE.md`); never test migration on real production
data or treat a Git push as a backup.

## L. Performance

Phase 1 uses a unique `(owner_id, symbol)` parent constraint and unique
`(instrument_id, version)` spec constraint, plus owner indexes; review actual
query plans before adding further compound indexes. If venue/type-qualified
symbols or effective dates are adopted later, update keys then. Add scoped
`(owner_id, date)` and `(owner_id, status/review_date)` indexes for actual
future query shapes. Unique per-owner keys must also work in PostgreSQL and
SQLite, including nullable venue normalization. Start paginating instrument
history, activity, fills, analyses/revisions, trades, journals and timeline;
filter by owner plus date/instrument/account/portfolio. Fetch bounded focus
items and summary aggregates on dashboard, not full user history or every
related fill. Avoid caching/queues until measured need.

## M. Migration strategy

`0014_instrument_registry.py` adds instrument/spec tables after the existing
migrations; it must not edit old tables or backfill guessed instrument
associations. Create an empty schema forward/backward rehearsal
and a seeded two-owner preservation rehearsal for both SQLite and PostgreSQL.
Keep explicit migration execution; application startup must not migrate.
Instrument definitions can be entered only from verified metadata and should
not silently reprice any existing investment. Phase 2a migration
`0015_portfolio_containers` adds portfolio/container metadata tables and a
unique `(owner_id, id)` Account index for composite, owner-matched foreign keys,
without rebuilding Account or modifying amounts. Reject destructive downgrade
if new records exist. Subsequent slices add holdings and trading entities
additively, establish ownership checks, then explicitly
reconcile legacy snapshots and net-worth formula with a rollback/backup plan.
Do not convert or delete existing holdings on Publish.

## N. Tests

Pure math tests: exact 1e-8 shares, oversized values, invalid ticks/quantity,
rounding and overflow; mini vs micro, LONG vs SHORT, multiple contracts,
points/ticks, fees/net, zero-risk rejection and R:R. Future fill tests: single
and multiple entries/exits, partial/full closure, ordering, weighted averages,
over-exit and frozen historical spec after new spec version. Service/API tests:
owner A cannot use B's IDs/specs, modify/export B's records or leak B's focus;
failed relationship writes roll back atomically. Migration tests: preexisting
Investment rows and net worth unchanged, existing export intact, fresh and
upgraded SQLite/PostgreSQL schemas, controlled rollback. Browser tests: form
validation, accessible disclosures of assumptions and privacy-sensitive
session handling. Run `bash scripts/prepublish_check.sh` before publishing;
that gate does not substitute for live sign-in and off-host restore testing.

## O. Small implementation sequence

1. **Phase 1 implemented locally:** exact Trading Math service, owned reference
   instruments/immutable versions, additive migration, scoped CRUD,
   format-2 owner-safe export and `/profit-engine` page with a
   non-posting hypothetical calculator. Validate tests and deployment
   independently. Preserve existing investments and net worth.
2. **Phase 2a (authorized organization-only implementation):** introduce
   private named portfolios and uniquely linked investment-account containers
   without converting legacy investments, changing balances or changing
   dashboard/net-worth totals. The separate holdings valuation policy is
   approved in principle, not a declaration that existing Accounts are
   cash-only. Atomic inter-account transfers remain deferred.
3. **Phase 2b (approved design only):** owner-reviewed opening snapshots and
   reconciliation, followed separately by actual activity/derived holdings.
   Switch valuation only per approved record/report after double-counting,
   backup and rollback gates pass; there is no blanket workspace switch.
4. **Phase 3–5:** analyses/areas/revisions, then plans/no-trade days, then
   fills and journaling; isolate each with own API and tests.
5. **Phase 6–7:** bounded attention/timeline, then measured analytics.
   Notifications, broker connections, live prices, options, tax lots and
   automatic trading remain out of scope.

For each slice, explain the input, stored facts, calculated outputs and owning
files in code comments; manually reconcile a representative user scenario
before moving on. This is an educational, traceable architecture rather than
a mandate to implement a seven-phase platform at once.

## P. Decisions requiring the owner's approval

1. **Settled in design:** one unique existing Account link per investment
   container; no second cash ledger or automatic portfolio valuation. Still
   unresolved **per real Account:** what cash and securities its current
   balance represents, which investments overlap, and what any separately
   approved non-income reconciliation must correct. Do not switch net worth
   before the exact report is approved.
2. **Settled in design:** existing Investments stay unchanged unless explicitly
   approved per record for an opening-position snapshot (not a fabricated
   purchase). The reconciliation report, backup and rollback gates are still
   needed for execution; future activity uses corrections/reversals, not
   destructive edits.
3. Confirm initial USD-only scope, allowable currencies/contract specs and
   authoritative source for tick size/value (including changes over time).
   Approve spec-version pinning and tick validation before live trade entry.
4. Select realized P&L matching/fee allocation for scaling and partial exits,
   and define whether realized R uses the original plan risk or an approved
   amendment after position-size changes. Clarify treatment of non-tick stock
   prices and sub-cent share math.
5. Approve default timezone/trading-session date, no-trade day rules and stale
   level review period. Portfolio access is already settled as private to
   one workspace; child-labeled names do not grant access to children.
6. Define recovery/export retention targets and verify published authentication
   before using the new features with real financial/trading data.

The reference registry and hypothetical calculator and Phase 2a organizational
work do not implement holdings, conversion or trading. No real-data conversion,
trading execution or dashboard repricing should proceed on assumptions.