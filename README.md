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
- Profit Engine Phase 1: workspace-private reference instruments with immutable
  specification versions and an exact hypothetical calculator at `/profit-engine`
  (not trades, live prices, holdings, postings, or net-worth changes)
- Phase 2a organization-only work: private named portfolios and investment-account
  containers linked to existing accounts; no holdings conversion, balance
  movement, or change to dashboard/net-worth calculations
- A dashboard with totals and net worth calculated from stored records
- Edit controls and confirmed permanent deletion for bills, debts, and investments;
  accounts and transaction/correction history retain their existing protections
- Business and dependent labels for transaction context
- Owner-scoped JSON export (format 3 includes instrument/specification history
  and portfolio/container metadata)
  and transaction CSV export; JSON export is not a verified restore/import tool

## Architecture

```text
frontend → API routes → Pydantic schemas → services → SQLAlchemy models → database
```

Financial calculations live in `services/` or `utils/`, never in browser
JavaScript. Money is stored as integer cents. Interest rates use thousandths of
a percent, investment quantities use integer units with eight decimal places,
and every timestamp is UTC.

See `docs/architecture.md`, `docs/data-model.md` and
`docs/PROFIT_ENGINE_REVIEW.md` for implemented scope versus future proposals. For a
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

Before every Publish, run the isolated prepublish check:

```bash
bash scripts/prepublish_check.sh
```

The check ignores the caller's database URL and clears PostgreSQL connection
settings. It requires real PostgreSQL migration/API tests in a disposable private
Unix-socket cluster, including an upgrade to the latest migration, and the full
Chromium browser suite. Missing tools fail rather than silently skipping tests.
PostgreSQL is declared by the PostgreSQL module and Nix package in `.replit`;
Python test dependencies are in `requirements.txt`. Restore these dependencies
if the toolchain is missing. The named `test` validation runs this same script.
No existing development or production database is migrated by this check.
Applying production schema or data changes remains a separate publishing step.

All financial pages, APIs, and exports require an authenticated Clerk user.
Serenity's signed cookie binds to the verified Clerk session and user. On every
protected request, the server checks that exact session is still active and
belongs to the same user. Revoking a Clerk session blocks its next request
(including exports and writes); another session for the same user is unaffected.
If Clerk's Backend API is unavailable, protected requests deny access until
it recovers. Each request incurs a Clerk lookup (up to an 8-second timeout);
there is no cross-request positive cache. Cookies issued before session binding
are rejected, so users must sign in again after this update.

Verified Clerk issuer and subject map to an internal Serenity user and a primary
workspace. Financial `owner_id` is the workspace ID, not the Clerk user ID;
inactive users cannot access records. See `docs/identity.md`. Migration 0011
creates these tables on empty databases. On databases with existing financial
rows, it refuses to rewrite owners without explicit, audited confirmation that
all old IDs belong to the configured Clerk issuer. Back up and verify the
database before this ownership migration; do not infer identity from email.
Migration 0012 widens investment quantity storage on PostgreSQL.
Migration 0014 additively creates instrument and specification tables without
modifying existing investments; it rejects destructive rollback if instrument
history exists. Migration 0015 adds empty portfolio/container tables and a
unique `(owner_id, id)` Account index to support owner-matched relationships;
it does not rebuild Accounts, migrate investments, or alter balances. Production
schema updates are a separate publishing step, not authorized by local work.

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