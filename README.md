# Serenity

Serenity is a personal finance and investment intelligence application built
with Python, FastAPI, SQLAlchemy, Pydantic, and a plain HTML/CSS/JavaScript
frontend.

The current application tracks:

- Financial accounts and balances by classification
- Manual account deposits and withdrawals with transaction history and derived balances
- Recurring and one-time bills
- Debts, including credit cards, with precise interest rates
- Investments with exact fractional quantities, cost basis, and current value
- Dashboard totals calculated from stored records

## Architecture

```text
frontend → API routes → Pydantic schemas → services → SQLAlchemy models → database
```

Financial calculations live in `services/` or `utils/`, never in browser
JavaScript. Money is stored as integer cents. Interest rates use thousandths of
a percent, and investment quantities use integer units with eight decimal
places.

## Local development

Python 3.11 is recommended.

```bash
python -m pip install -r requirements.txt
export DATABASE_URL=sqlite:///./serenity.db
alembic upgrade head
SERENITY_DEV=1 python main.py
```

Open <http://localhost:8000>. API documentation is available at
<http://localhost:8000/docs>.

Without `DATABASE_URL`, Serenity also defaults to `sqlite:///./serenity.db`.

## PostgreSQL on Replit

Replit supplies `DATABASE_URL` for its managed development and production
PostgreSQL databases. Serenity normalizes that URL for psycopg automatically.
Schema changes are represented by Alembic migrations. Apply migrations to the
development database, verify them there, and use Replit Publish to review and
apply the development-to-production schema diff.

Production starts with:

```bash
uvicorn main:app --host 0.0.0.0 --port "$PORT"
```

It does not perform schema mutations at application startup.

## Tests

```bash
pytest
```

Tests use isolated SQLite databases and never touch `serenity.db` or PostgreSQL.
The Accounts browser tests launch Chromium with Playwright and route the real
page and API through the in-memory FastAPI test client. Chromium must be
available on `PATH` (it is provided in the Replit workspace). The named
`test` validation runs the full suite, including these browser checks.

## Project direction

Serenity is developed one tested vertical slice at a time:

```text
STABILIZE → TRANSACTIONS → INCOME + BUDGET → FINANCIAL MODELING
→ PORTFOLIO / PROFIT ENGINE → TRADING ANALYTICS
```

GitHub is the source of truth. See `docs/architecture.md` and
`docs/data-model.md` for implementation details.