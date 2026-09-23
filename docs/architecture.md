# Serenity Architecture

## Layered flow

```text
frontend/  HTML, CSS, JavaScript; input and display only
    ↓ HTTP + JSON
api/       FastAPI routes; HTTP concerns and status codes
    ↓
schemas/   Pydantic input validation and response shapes
    ↓
services/  business rules and financial calculations
    ↓
models/    SQLAlchemy persistence models
    ↓
storage/   SQLite or PostgreSQL connection
```

Shared exact-value helpers live in `utils/`. Automated tests live in `tests/`.

## Main domains

| Domain | API | Schemas | Service |
|---|---|---|---|
| Accounts | `api/accounts.py` | `schemas/account.py` | `account_service`: creates accounts, derives current balances, account-only totals |
| Transactions | `api/transactions.py` | `schemas/transaction.py` | `transaction_service`: records, edits and soft-deletes transactions; keeps correction history; decides each transaction's sign |
| Bills, debts, investments | `api/finance.py` | `schemas/finance.py` | `finance_service`: obligations, liabilities, starting-position investments and summaries |
| Dashboard | `api/dashboard.py` | `schemas/dashboard.py` | `dashboard_service`: combines independent summaries |

- `account_service` asks `transaction_service` for active transaction balance
  changes; it never decides direction itself.
- Credit cards are Debts, not Accounts, which prevents double-counting.

## Exact values

- Money is stored as integer cents.
- Debt APR is stored as thousandths of a percent. `6.875%` becomes `6875`.
- Investment quantity is stored as integer units where one whole unit equals
  `100,000,000` stored units.
- Recurring bills are summed in twelfths of a cent and rounded once using
  round-half-up. Monthly bills contribute 12/12, quarterly 4/12, annual 1/12,
  and one-time bills are excluded.

## Database lifecycle

`storage/database.py` selects SQLite when no database URL is supplied and
PostgreSQL when Replit supplies `DATABASE_URL`. Alembic migrations are the
schema source of truth.

Application startup does not create or alter tables. Local development runs
`alembic upgrade head` before starting. On Replit, migrations are applied to
the development database and Publish reviews the development-to-production
schema diff.

**Known limitation:** Replit Publish copies table structure only. A migration
that also changes data, such as `0004` renaming transaction types, does not run
against production automatically. Before production has real transactions,
decide how data migrations will reach it.

## API paths

Serenity APIs use `/serenity-api`:

- `/serenity-api/accounts`
- `/serenity-api/accounts/{id}/transactions`
- `/serenity-api/accounts/{id}/transaction-corrections`
- `/serenity-api/transactions/options`
- `/serenity-api/bills`
- `/serenity-api/debts`
- `/serenity-api/investments`
- `/serenity-api/dashboard/summary`
- `/serenity-api/finance/summary`

## Tests

- `pytest` runs everywhere. API and service tests use in-memory SQLite;
  `test_migrations.py` builds a SQLite file from migrations.
- Browser tests (`test_accounts_browser.py`) need Playwright and Chromium and
  run on Replit.

## Development rules

- Keep routes thin.
- Keep calculations out of JavaScript.
- Store authoritative facts and calculate derived results.
- Add a migration whenever a model changes.
- Review generated migrations before applying them.
- Never collect bank credentials.