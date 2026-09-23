# Serenity

Serenity is a Python/FastAPI personal finance and investment intelligence app.
GitHub is the source of truth. It is also the owner's software-engineering
learning project, so readable, commented code is a product requirement.

## Rules for Replit Agent (read first)

- **Do not reformat, compact or "clean up" existing files.** Keep every
  docstring and explanatory comment exactly as written. Removing comments to
  shorten files has happened before and is not acceptable.
- Change only the lines a task requires. Don't merge lines, shorten names or
  rewrite working code in a different style.
- Don't add frameworks or dependencies without being asked.
- Never put financial calculations in JavaScript.
- Never make production run `alembic upgrade head` (see "Database and publishing").
- If a task conflicts with these rules or the financial rules below, stop and ask.

## Run and verify

- Replit manages Python dependencies from `requirements.txt`; do not run a global pip install in post-merge setup.
- Before every Publish: `SERENITY_DEVELOPMENT_DATABASE=1 bash scripts/prepublish_check.sh`
- Local schema: `DATABASE_URL=sqlite:///./serenity.db alembic upgrade head`
- Local app: `SERENITY_DEV=1 DATABASE_URL=sqlite:///./serenity.db python main.py`
- Tests: `pytest` (includes Chromium/Playwright Accounts browser checks;
  Chromium is required and tests fail if it is unavailable)

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
- Transaction amounts are positive; Income/Expense sets direction. Transfers are deferred.
- Store debt APR as milli-percent (`6.875%` → `6875`).
- Store investment quantity in 1e-8 integer units.
- Normalize recurring bills exactly and round the combined total once.
- Exclude one-time bills from recurring monthly totals.
- Model credit cards as Debts, never as Accounts.
- Net worth = account balances + investment value − debt balances, in cents.
- Keep the current Investment feature as a temporary starting-position model.
- Keep account, transaction, finance and dashboard services separate.
- All timestamps are time-zone-aware UTC.

## Database and publishing

- Application startup must not create or alter tables.
- In development, generate migrations with Alembic, review them, apply them
  with `alembic upgrade head`, and run the tests.
- Replit Publish reviews and applies the development-to-production schema
  structure. Production does not run Alembic.
- Before Publish, run
  `SERENITY_DEVELOPMENT_DATABASE=1 bash scripts/prepublish_check.sh` against
  the explicitly selected development PostgreSQL database.
- Data corrections are separate, explicitly authorized operations; Publish does
  not make production data safe automatically.
- Production runs Uvicorn through the Serenity artifact manifest.
- The remaining artifact manifests are Replit-managed metadata; the Node/Vite
  application code and PNPM workspace have been removed.

## Routing

Serenity APIs use `/serenity-api`. Do not move them back to `/api`; `/api` is
reserved by retired Replit artifact metadata.

## Product direction

Stabilize first, then build Transactions as a separate tested vertical slice.
Do not implement the full Portfolio, Trading, or modeling architecture at once.