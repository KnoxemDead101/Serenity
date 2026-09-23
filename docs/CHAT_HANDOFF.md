# Serenity — chat handoff

Prepared September 23, 2026. Use this as context for continued product brainstorming.
Inspect the current repository before implementing; this is a snapshot, not a
replacement for the code or current verification results.

## Product and goals

Serenity is a personal finance application. The near-term goal is to begin using
it reliably for real financial records while retaining ownership of the source
and the option to move hosting away from Replit later.

Replit hosts the app for now. The source repository is
https://github.com/KnoxemDead101/Serenity (public at the time of this check).
Source ownership, database backups, and control of the sign-in provider are
separate concerns: a GitHub copy alone is not a full operational backup.

## What exists

- Accounts, income/expense transactions, correction history, and calculated balances.
- Bills, debts, investments, dashboard totals and net worth.
- Business/dependent context and record edit/deactivate controls.
- Income profiles for planned income; these are not posted transactions.
- JSON backup export and transaction CSV export. There is no verified full
  database restore or automatic import workflow implied by those exports.
- Responsive dark interface with Python-owned financial calculations.
- Per-user financial data isolation tied to verified Clerk user IDs.

## Technical baseline

- Python 3.11, FastAPI, SQLAlchemy, Pydantic, Alembic.
- Plain HTML/CSS/JavaScript frontend; no Node server needed for the core app.
- SQLite supported; PostgreSQL supported through configured DATABASE_URL.
- Integer money and quantity storage; UTC timestamps.
- Migrations run explicitly before deploying, not at application startup.
- Runtime configuration is described by .env.example; .env is not auto-loaded.
- Read README.md, docs/HOSTING.md, docs/auth-verification.md and replit.md.

## Sign-in and session protection

- Real RSA signature and trusted issuer/origin checks precede the Clerk token exchange.
- Signed HttpOnly Serenity cookies bind a user to the exact verified Clerk session.
- Each protected request checks Clerk for active status and matching ownership.
  Revocation blocks the next checked request; Clerk failure denies access.
- This adds a network dependency to every protected request (8-second timeout).
  Fast public endpoints do not prove fast authenticated endpoints.
- A protected API 401 clears displayed financial content and unsaved form
  fields, then offers explicit sign-in or manual retry without redirect loops.
- Cross-tab sign-out and visibility-time session checks are included.
- Safe return paths reject external redirect destinations.
- Previously downloaded files or screenshots cannot be revoked by the app.

## Verification performed

- 205 tests passed, including required Chromium/Playwright browser tests.
  Two existing test-library deprecation warnings remain.
- Isolated temporary SQLite database: migrations and startup succeeded without
  Replit or Clerk environment variables. Sign-in page returned 200; protected
  pages redirected (307); financial APIs denied access (401).
- 50 local TestClient calls to the public auth-config endpoint measured
  median 2.13 ms, maximum 4.20 ms. This is a small smoke measurement, NOT a
  load test, production benchmark, or measurement of real Clerk latency.
- Development web workflow restarted successfully.
- No independent external-host deployment or production user sign-in was
  established by these tests.

## Before entering real financial records

Complete the existing published sign-in verification: actual production login,
authenticated read/write with disposable data, refresh, sign-out, and denied
access after sign-out. Verify the published database and backups are appropriate.
Do not treat a successful Preview sign-in as production verification.

The same email may be used, but a Serenity account is separate from a Replit
account. Development and production Clerk users are separate. A second email is
useful for isolation testing, not required for the owner's normal use.

## Hosting outside Replit

The application runtime is portable, but a server move is NOT just a file copy.
Follow docs/HOSTING.md: dependencies, persistent database, explicit migrations,
stable SESSION_SECRET, HTTPS, process supervision, backups, exact trusted origins,
and outbound Clerk/CDN connectivity are all required.

Replit-managed Clerk cannot be exported into independently managed hosting.
A future move needs a supported independent authentication setup and a tested,
audited old-to-new user-ID ownership migration. Do not automatically link
financial ownership by matching email. Keep a rollback backup.

The application is not yet proven on an owned server. Its database backup/restore
and authentication migration procedures must be rehearsed before a real move.
Do not change managed keys now or weaken authentication to make migration easier.

## Suggested brainstorming priorities

1. First-use experience: the minimum setup needed before recording real activity.
2. Backup reliability: automated encrypted backups and a tested restore procedure.
3. Daily workflow: income plans versus actual deposits, transaction entry and corrections.
4. Reporting priorities: cash flow, bill planning and actionable summaries.
5. Performance: measure real authenticated requests before changing security checks.
6. Future hosting: choose a target server and identity-provider ownership plan
   before attempting migration.

## Instructions for the next chat

Help brainstorm from this baseline; do not rebuild or replace the app by default.
Separate confirmed features from proposals. Preserve ownership isolation,
cryptographic authentication, accurate financial arithmetic and existing records.
Inspect the latest code/tests before making changes. Do not assume GitHub includes
database contents, secrets, Clerk users or a running deployment.