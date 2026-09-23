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
| Businesses | `api/businesses.py` | `schemas/business.py` | `business_service`: business labels, uniqueness, editing and lifecycle |
| Dependents | `api/dependents.py` | `schemas/dependent.py` | `dependent_service`: dependent labels, uniqueness, editing and lifecycle |
| Backup/export | `api/export.py` | plain JSON/CSV | `export_service`: complete, exact-value backup and transaction CSV |
| Dashboard | `api/dashboard.py` | `schemas/dashboard.py` | `dashboard_service`: combines independent summaries; owns the net-worth formula |

- `account_service` asks `transaction_service` for active transaction balance
  changes; it never decides direction itself.
- Database-dependent transaction rules (inactive accounts and business/dependent
  links) live in `transaction_service` and are returned as readable HTTP 422
  responses by the API.
- Each total has exactly one formula: `account_service.total_balance_cents`,
  `finance_service.total_debt_balance_cents`,
  `finance_service.total_investment_value_cents`, and
  `finance_service.normalized_monthly_bill_total_cents`.
- Net worth (`dashboard_service.calculate_net_worth_cents`) =
  account balances + investment value - debt balances, all in cents,
  converted to dollars once at the end.
- Credit cards are Debts, not Accounts, which prevents double-counting.
- Business and dependent links are labels only: they never change transaction
  amounts or balances. A business link requires Business classification, and
  newly linked labels must be active.

## Exact values

- Money is stored as integer cents.
- Debt APR is stored as thousandths of a percent. `6.875%` becomes `6875`.
- Investment quantity is stored as integer units where one whole unit equals
  `100,000,000` stored units.
- Recurring bills are summed in twelfths of a cent and rounded once using
  round-half-up. Monthly bills contribute 12/12, quarterly 4/12, annual 1/12,
  and one-time bills are excluded.
- Every timestamp is time-zone-aware UTC (`DateTime(timezone=True)`, migration
  `0005`). The browser converts to local time only for display.
- Records are edited and deactivated rather than hard-deleted. Inactive
  accounts remain in balances but cannot receive new transactions; inactive
  bills, debts and investments leave their corresponding finance totals.

## Database lifecycle

`storage/database.py` selects SQLite when no database URL is supplied and
PostgreSQL when Replit supplies `DATABASE_URL`. Alembic migrations are the
schema source of truth.

Application startup never creates or alters tables. On Replit, migrations are
applied to the development database and Publish reviews and applies the
development-to-production schema structure.

### Development

1. Change a model.
2. Generate a migration with
   `alembic revision --autogenerate -m "describe the change"`.
3. Read and edit the generated file, then run `alembic upgrade head`.
4. Run `pytest`.

Prefer generating migrations against the development PostgreSQL database,
because it reports database types most accurately. SQLite remains useful for
local development and isolated tests.

### Production

Replit Publish applies the verified development schema structure to production
before the app starts. Production does not run Alembic. Before every Publish,
run `SERENITY_DEVELOPMENT_DATABASE=1 bash scripts/prepublish_check.sh` against
the explicitly selected development PostgreSQL database. The check confirms
the development database is at the latest revision and runs the tests; it does
not certify production data.

Data-changing migrations require particular care: Publish handles schema
structure, but it does not automatically make production data correct. Any
future production data correction requires separate authorization and a
reviewed procedure; do not add direct managed-production DDL or run an
unreviewed correction.

## API paths

Serenity APIs use `/serenity-api`:

- `/serenity-api/accounts`
- `/serenity-api/accounts/{id}/transactions`
- `/serenity-api/accounts/{id}/transaction-corrections`
- `/serenity-api/transactions/options`
- `/serenity-api/businesses` and `/serenity-api/dependents` (with edit,
  deactivate and reactivate actions)
- `/serenity-api/bills`
- `/serenity-api/debts`
- `/serenity-api/investments`
- `/serenity-api/dashboard/summary`
- `/serenity-api/finance/summary`
- `/serenity-api/export` (complete JSON backup) and
  `/serenity-api/export/transactions.csv`

## Backup / export

The JSON export includes every financial record, including inactive rows,
soft-deleted transactions and correction history. Monetary values remain exact:
exports include integer storage units and display strings, never floats. The
export records the Alembic schema revision and does not provide restore/import.
The CSV export is a transaction-history convenience file and marks cells that
could be interpreted as spreadsheet formulas.

These endpoints expose sensitive financial data. They are currently
unauthenticated, so the published application must be access-restricted
(for example, Replit Invite only) before publishing. This is a deployment
requirement, not an application authentication mechanism.

## Tests

- `pytest` runs everywhere. API and service tests use in-memory SQLite;
  `test_migrations.py` builds SQLite files from the migrations and checks
  upgrade/downgrade behavior.
- Browser tests (`test_accounts_browser.py`) require Playwright and Chromium
  and fail when Chromium is unavailable.

## Development rules

- Keep routes thin.
- Keep calculations out of JavaScript.
- Store authoritative facts and calculate derived results.
- Add a migration whenever a model changes.
- Review generated migrations before applying them.
- Keep explanatory comments; don't compact files.
- Never collect bank credentials.