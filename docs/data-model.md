# Serenity Data Model

All tables have integer primary keys and UTC `created_at`/`updated_at`
timestamps. Alembic migrations are the executable schema source of truth.

## Nothing is hard-deleted

Financial history is retained. Accounts, bills, debts, investments,
businesses and dependents are deactivated with `active = false`; transactions
are soft-deleted with `deleted_at` and a correction-history snapshot.

- Inactive accounts are omitted from new-transaction choices and cannot receive
  new transactions, but still count toward balances and net worth.
- Inactive bills leave bill counts and recurring totals.
- Inactive debts and investments leave debt/investment totals and net worth.
- Inactive businesses and dependents cannot be newly linked; existing links
  remain valid for historical transactions.

Every record type can be edited and reactivated.

## accounts

An Account is an owned financial container. Credit cards are Debts.

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

**Until the Portfolio milestone:** Brokerage or Retirement opening balances
should be cash only; holdings are entered as Investments to avoid counting
the same money twice.

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