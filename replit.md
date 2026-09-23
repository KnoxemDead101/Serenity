# Serenity

Serenity is a Python/FastAPI personal finance and investment intelligence app.
GitHub is the source of truth.

## Run and verify

- Replit manages Python dependencies from `requirements.txt`; do not run a global pip install in post-merge setup.
- Local schema: `DATABASE_URL=sqlite:///./serenity.db alembic upgrade head`
- Local app: `SERENITY_DEV=1 DATABASE_URL=sqlite:///./serenity.db python main.py`
- Tests: `pytest` (includes Chromium/Playwright Accounts browser checks)
- Migration check: `DATABASE_URL=sqlite:///./serenity.db alembic current`

## Stack

- Python 3.11, FastAPI, Uvicorn
- SQLAlchemy and Alembic
- SQLite locally and in tests
- Replit-managed PostgreSQL for persistent development/production
- Plain HTML, CSS, and JavaScript

## Architecture

- `main.py` wires routes and static frontend files.
- `api/` owns HTTP concerns.
- `schemas/` validates input and defines response shapes.
- `services/` owns financial rules and calculations.
- `models/` defines persistence.
- `storage/database.py` selects SQLite or PostgreSQL from `DATABASE_URL`.
- `migrations/` is the schema source of truth.

## Financial rules

- Store money as integer cents.
- Derive account balances from opening balances and signed transaction activity.
- Store debt APR as milli-percent (`6.875%` → `6875`).
- Store investment quantity in 1e-8 integer units.
- Normalize recurring bills exactly and round the combined total once.
- Exclude one-time bills from recurring monthly totals.
- Model credit cards as Debts, never as Accounts.
- Keep the current Investment feature as a temporary starting-position model.
- Keep account, finance, and dashboard aggregation services separate.

## Database and publishing

- Application startup must not create or alter production tables.
- Apply Alembic migrations to the development database and verify them.
- Replit Publish reviews and applies the development-to-production schema diff.
- Production runs Uvicorn through the Serenity artifact manifest.
- The remaining artifact manifests are Replit-managed metadata; the Node/Vite
  application code and PNPM workspace have been removed.

## Routing

Serenity APIs use `/serenity-api`. Do not move them back to `/api`; `/api` is
reserved by retired Replit artifact metadata.

## Product direction

Stabilize first, then build Transactions as a separate tested vertical slice.
Do not implement the full Portfolio, Trading, or modeling architecture at once.