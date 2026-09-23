# Serenity

Serenity is a personal finance and investment intelligence application built
with Python, FastAPI, SQLAlchemy, Pydantic, and a plain HTML/CSS/JavaScript
frontend. It is built around one real financial system first, and it is also a
software-engineering learning project, so the code is written to be read.

The current application tracks:

- Financial accounts and balances by classification
- Income and expense transactions with merchant, category, classification and
  a full correction history; balances are calculated, never stored
- Recurring and one-time bills
- Debts, including credit cards, with precise interest rates
- Investments (temporary starting positions) with exact fractional quantities
- A dashboard with totals and net worth calculated from stored records
- Edit and deactivate lifecycle controls; records are retained rather than hard-deleted
- Business and dependent labels for transaction context
- Full JSON backup and transaction CSV export

## Architecture

```text
frontend → API routes → Pydantic schemas → services → SQLAlchemy models → database
```

Financial calculations live in `services/` or `utils/`, never in browser
JavaScript. Money is stored as integer cents. Interest rates use thousandths of
a percent, investment quantities use integer units with eight decimal places,
and every timestamp is UTC.

See `docs/architecture.md` and `docs/data-model.md` for details. For a
non-Replit deployment, read `docs/HOSTING.md` first: the managed Clerk tenant
cannot be exported and financial-record ownership needs a verified migration.

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

## PostgreSQL and publishing on Replit

Replit supplies `DATABASE_URL` for its managed development and production
PostgreSQL databases, and Serenity normalizes that URL for psycopg
automatically.

Before every Publish, run the prepublish check with an explicitly selected
development database:

```bash
SERENITY_DEVELOPMENT_DATABASE=1 bash scripts/prepublish_check.sh
```

The check refuses SQLite and refuses to run unless the development-database
confirmation is explicit. It migrates the development database, confirms it is
at the latest migration, and runs the tests. Replit Publish then compares and
applies the development-to-production schema structure. This does not validate
or transform production data automatically.

All financial pages, APIs, and exports require an authenticated Clerk user.
Serenity's signed cookie binds to the verified Clerk session and user. On every
protected request, the server checks that exact session is still active and
belongs to the same user. Revoking a Clerk session blocks its next request
(including exports and writes); another session for the same user is unaffected.
If Clerk's Backend API is unavailable, protected requests deny access until
it recovers. Each request incurs a Clerk lookup (up to an 8-second timeout);
there is no cross-request positive cache. Cookies issued before session binding
are rejected, so users must sign in again after this update.

If an already-open page receives a protected API 401, the browser immediately
removes displayed financial values and any unsaved form contents, then shows
sign-in and manual retry choices. It does not silently retry or redirect during
Clerk outages. Retry checks the session once and reloads only if valid; sign-in
returns only to a validated same-origin path. No draft or token is persisted.

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
page and API through the in-memory FastAPI test client. They require Chromium
to be available on `PATH`; without it, those tests fail rather than skip. The
named `test` validation runs the full suite, including these browser checks.

## Project direction

Serenity is developed one tested vertical slice at a time:

```text
STABILIZE → BUSINESS + DEPENDENTS → INCOME PROFILES → GOALS → BUDGET
→ FINANCIAL TIMELINE → PROJECTIONS / SCENARIOS
→ PORTFOLIO / PROFIT ENGINE → TRADING ANALYTICS
```

GitHub is the source of truth. See `docs/architecture.md` and
`docs/data-model.md` for implementation details.