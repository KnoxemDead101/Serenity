# Serenity Data Model

All tables have integer primary keys and UTC `created_at`/`updated_at`
timestamps. Alembic migrations are the executable schema source of truth.

## Record removal and history

Bills, debts, and investments can be permanently deleted through owner-scoped
DELETE endpoints after browser confirmation. Deletion removes the stored row,
its contribution to totals, and its presence in future exports. Re-adding an
item creates a new record; there is no undo. Prior backups can retain copies.
Existing inactive records are not automatically purged: the UI lets their
owner explicitly delete them too. Legacy deactivation/reactivation endpoints
remain for compatibility, but the finance UI uses Delete.

Accounts, businesses and dependents retain deactivation with `active = false`;
transactions remain soft-deleted with `deleted_at` and a correction-history
snapshot. Permanent finance deletion does not change account or transaction history.

- Inactive accounts are omitted from new-transaction choices and cannot receive
  new transactions, but still count toward balances and net worth.
- Inactive bills leave bill counts and recurring totals.
- Inactive debts and investments leave debt/investment totals and net worth.
- Inactive businesses and dependents cannot be newly linked; existing links
  remain valid for historical transactions.

Instrument references follow their own archive/reactivate policy below;
finance deletion follows the policy above. Portfolios and investment-account
containers are archived, not deleted; archival does not move or devalue assets.

## accounts

An Account is an owned financial container. Credit cards are Debts. A
Phase 2a InvestmentAccount may link to one existing Account; this link is
organizational metadata, not a second balance or proof that its current
opening balance represents cash only.

| Column | Storage |
|---|---|
| `name` | text |
| `account_type` | checking, savings, cash, business checking, brokerage, retirement, trading, or other |
| `classification` | personal, business, investment, or trading display value |
| `opening_balance_cents` | integer cents |
| `institution` | optional text |
| `notes` | optional text |
| `active` | boolean |

Current balance is derived: opening balance + Income transactions − Expense
transactions (deleted transactions ignored). Direction is decided only by
`services/transaction_service.signed_amount_cents()`.

## transactions

Financially meaningful money entering or leaving one account. Amounts are
always positive; `transaction_type` controls direction.

| Column | Storage |
|---|---|
| `account_id` | foreign key to accounts |
| `date` | transaction date |
| `transaction_type` | Income or Expense (Transfer is deferred) |
| `classification` | Personal, Business, Investment, or Trading; defaults to account classification |
| `amount_cents` | positive integer cents |
| `description` | required text: reason money moved |
| `merchant` | optional text |
| `location` | optional text |
| `category` | optional text; suggestions come from `TRANSACTION_CATEGORIES` |
| `subcategory` | optional text |
| `business_id` | optional foreign key to `businesses` (migration `0007`) |
| `dependent_id` | optional foreign key to `dependents` (migration `0007`) |
| `created_at` / `updated_at` | UTC timestamps |
| `deleted_at` | optional UTC timestamp |

Active history is ordered by date descending, then ID descending. Only active
transactions contribute to account and dashboard balances. Dashboard account
totals group by the account's classification, while transaction classification
records what the money was for.

### Business and dependent links

Links are labels only; they never change an amount or balance. A linked label
must exist and must be active when newly selected. Editing may retain a link
to a label that was deactivated later.

A business link requires `Business` classification. A blank classification
becomes Business; another explicit classification is rejected. Business
classification without a business link remains valid. Shared child costs use
a separate `Shared / All Children` dependent; there are no percentage
allocations, preventing shared costs from being double-counted.

Migration `0004_align_transactions_v02` renamed existing `Deposit` rows to
`Income` and `Withdrawal` rows to `Expense`, and copied each account's
classification onto existing transactions.

## transaction_corrections

Each edit and deletion records an append-only snapshot of the prior
transaction, in the same commit as the change. Edits also record the resulting
state; deletions retain the row with `deleted_at` set but remove it from active
history. The corrections list is read-only.

| Column | Storage |
|---|---|
| `account_id` | foreign key to accounts |
| `transaction_id` | foreign key to retained transaction |
| `action` | Updated or Deleted |
| `changed_at` | UTC timestamp |
| `before` | JSON snapshot: date, type, classification, amount cents, description, merchant, location, category, subcategory |
| `after` | JSON snapshot after edit; null for deletion |

History is never rewritten. Snapshots saved before migration 0004 still say
`Deposit`/`Withdrawal` and lack newer keys; the API returns those keys as null.
Snapshots after migration 0007 retain linked business/dependent IDs and names
as they were at the time, so later renames do not rewrite history.

## bills

A Bill is an obligation, not proof payment occurred.

| Column | Storage |
|---|---|
| `name` | text |
| `amount_cents` | non-negative integer cents |
| `due_date` | date |
| `frequency` | monthly, quarterly, annual, or one-time display value |
| `category` | optional text |
| `notes` | optional text |
| `active` | boolean, default true |

One-time bills are excluded from recurring monthly totals.

## debts

Debts include credit cards, student loans, personal loans, mortgages, auto
loans, medical debt, and other liabilities.

| Column | Storage |
|---|---|
| `name` | text |
| `debt_type` | validated debt type |
| `balance_cents` | non-negative integer cents |
| `interest_rate_milli` | thousandths of a percent |
| `minimum_payment_cents` | non-negative integer cents |
| `due_date` | optional date |
| `notes` | optional text |
| `active` | boolean, default true |

For example, `6.875%` is stored as `6875`.

## investments

The current Investment model is a retained starting-position feature. The
future Portfolio milestone will replace direct cost-basis and current-value
entry with Holdings and Investment Transactions.

| Column | Storage |
|---|---|
| `name` | text |
| `ticker` | optional text |
| `quantity_units` | integer, eight decimal places |
| `cost_basis_cents` | non-negative integer cents |
| `current_value_cents` | non-negative integer cents |
| `notes` | optional text |
| `active` | boolean, default true |

For example, `0.12345678` units is stored as `12,345,678`.

Existing Brokerage, Retirement or Trading balances may already include
securities. Never silently interpret them as cash-only or automatically add
holdings to net worth. Continue the current dashboard treatment until
per-record reconciliation and an approved valuation switch; do not fabricate
historical purchases from existing Investment entries.

## portfolios and investment_accounts (Phase 2a organization)

`portfolios` are workspace-private, named organizational groups, including
empty groups. `investment_accounts` are named metadata containers with exactly
one portfolio membership and one owner-checked link to an existing Account.
They do not store a second cash balance, quantity, valuation, or activity.

| Table | Fields and constraints |
|---|---|
| `portfolios` | ID, `owner_id`, name, optional notes, active, UTC timestamps; unique `(owner_id, id)` parent key |
| `investment_accounts` | ID, `owner_id`, name, optional notes, `portfolio_id`, `account_id`, active, UTC timestamps; one link per Account including archived containers |

New relationships match owner and ID at both the service and foreign-key
levels. Migration `0015_portfolio_containers` adds an Account unique
`(owner_id, id)` index (without rebuilding Accounts) for the composite
owner/Account reference; it adds no legacy Investment associations or data
backfill. The cash-account link cannot be replaced after creation. Portfolio
membership can be changed without a transfer or balance change. Portfolios
cannot be archived while they contain active containers; archived containers
retain their Account link, preventing reuse. Archived records remain exportable.
These tables do not participate in the current net-worth formula.

## instruments and instrument_specifications (Phase 1)

Migration `0014_instrument_registry` additively creates two workspace-private
tables; it does not change existing `investments` or net worth.
`instruments` stores owner ID, immutable uppercase symbol and active flag;
the owner/symbol pair is unique. Owners can archive/reactivate references but
cannot delete their version history through the API. Immutable, sequential
`instrument_specifications` store the instrument ID, matching owner ID, version,
symbol, name, service-validated unchangeable asset type (`STOCK`, `ETF` or
`FUTURE`), optional exchange,
USD currency, tick size and point value as positive BIGINT units of 1e-8, and
creation time. Metadata edits append a new version, leaving older versions
intact. Asset type remains fixed via service validation; it is not duplicated
on the parent row. Archived specifications remain usable by ID for hypothetical
historical calculations. USD is the only supported currency; no prices are
fetched automatically, no executed trades or account movements are stored.
The protected `/profit-engine` page displays a hypothetical calculator, not
positions or financial holdings.

Owner-scoped JSON export format 3 includes both reference tables and all spec
versions plus portfolios and investment-account links; this is not a tested
import/restore format. A nonempty instrument table prevents destructive
downgrade of migration 0014, and nonempty portfolio/container tables prevent
destructive downgrade of 0015. For future holdings and trade history, see
[PROFIT_ENGINE_REVIEW.md](PROFIT_ENGINE_REVIEW.md).

## businesses

A Business is a lightweight label for business activity, not a separate
accounting system.

| Column | Storage |
|---|---|
| `name` | text, unique; application also rejects case-insensitive duplicates |
| `notes` | optional text |
| `active` | boolean, default true |

## dependents

A Dependent is a lightweight label for spending on a child. Serenity stores no
birthdates or government ID numbers.

| Column | Storage |
|---|---|
| `display_name` | text, unique; application also rejects case-insensitive duplicates |
| `notes` | optional text |
| `active` | boolean, default true |