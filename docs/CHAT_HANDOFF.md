# Serenity — chat handoff

Updated September 29, 2026. Use this as context for continued product brainstorming.
Inspect the current repository before implementing; this is a snapshot, not a
replacement for the code or current verification results.

## Product and goals

Serenity is a personal finance application. The near-term goal is to begin using
it reliably for real financial records while retaining ownership of the source
and the option to move hosting away from Replit later.

There is **no near-term public-release goal**. Keep access invitation-only while
planning for selected additional users. Design account settings and ownership
boundaries early so later development does not require an expensive rewrite.

Replit hosts the app for now. The source repository is
https://github.com/KnoxemDead101/Serenity (public at the time of this check).
Source ownership, database backups, and control of the sign-in provider are
separate concerns: a GitHub copy alone is not a full operational backup.

## What exists

- Accounts, income/expense transactions, correction history, and calculated balances.
- Bills, debts, investments, dashboard totals and net worth.
- Phase 1 Profit Engine reference instruments with workspace-private,
  archiveable parent records and append-only spec versions (USD tick size and
  point value stored exactly). `/profit-engine` offers a hypothetical calculator
  only; it does not record trades, fetch live prices or change net worth.
  Archived specs remain calculable by ID for reproducibility.
- Phase 2a organization-only implementation work adds private named portfolios
  (including empty ones) and investment-account containers, each linked to one
  existing Account and one portfolio. Linking and regrouping never post cash,
  convert investments, or alter dashboard/net-worth totals. An archived
  container retains its unique cash-account link.
- Business/dependent context and record edit/deactivate controls.
- Bills, debts and investments now have confirmed permanent deletion, including
  previously inactive items. No automatic cleanup of existing records occurs.
  Accounts, transactions and correction history retain their protections.
  Deletion removes rows from future totals/exports, not from existing backups.
- Income profiles for planned income; these are not posted transactions.
- JSON backup export and transaction CSV export. There is no verified full
  database restore or automatic import workflow implied by those exports.
  JSON format 3 includes instruments, complete spec-version history, and
  portfolio/container metadata; it does not restore or import data.
  Database-native rehearsal instructions and current evidence are maintained
  separately in [BACKUP_RESTORE.md](BACKUP_RESTORE.md); exports are not that backup.
- Responsive dark interface with Python-owned financial calculations.
- Financial records isolated by Serenity workspace IDs, mapped from verified
  Clerk issuer and subject to an internal user and primary workspace.

## Technical baseline

- Python 3.11, FastAPI, SQLAlchemy, Pydantic, Alembic.
- Plain HTML/CSS/JavaScript frontend; no Node server needed for the core app.
- SQLite supported; PostgreSQL supported through configured DATABASE_URL.
- Integer money and quantity storage; UTC timestamps.
- Migration 0013 widens all 11 stored monetary-cent fields to BigInteger.
  Migration 0012 already widened investment quantities. Existing input limits
  remain; unsafe narrowing rollbacks are rejected before changing columns.
- Migration 0014 adds instrument/spec tables; it leaves existing Investments
  untouched and refuses a destructive downgrade while instrument data exists.
- Migration 0015 adds portfolio/container tables and an Account `(owner_id, id)`
  unique index for owner-matched foreign keys without rebuilding Accounts.
  Existing Investments and balances are neither transformed nor backfilled.
- Migrations run explicitly before deploying, not at application startup.
- Runtime configuration is described by .env.example; .env is not auto-loaded.
- Read README.md, docs/HOSTING.md, docs/auth-verification.md and replit.md.

## Sign-in and session protection

- Real RSA signature and trusted issuer/origin checks precede the Clerk token exchange.
- Signed HttpOnly Serenity cookies bind a user to the exact verified Clerk session.
- Each protected request checks Clerk for active status and matching ownership.
  Revocation blocks the next checked request; Clerk failure denies access.
- Internal users can be deactivated (403), without losing their workspace records.
- Migration 0011 requires explicit issuer-provenance confirmation for existing
  financial owner IDs. Migration 0012 widens PostgreSQL investment quantity.
- This adds a network dependency to every protected request (8-second timeout).
  Fast public endpoints do not prove fast authenticated endpoints.
- A protected API 401 clears displayed financial content and unsaved form
  fields, then offers explicit sign-in or manual retry without redirect loops.
- Cross-tab sign-out and visibility-time session checks are included.
- Safe return paths reject external redirect destinations.
- Previously downloaded files or screenshots cannot be revoked by the app.

## Verification performed

- Phase 1 instrument/calculator/migration work passed local tests, including
  isolated migration, ownership and browser checks. This does not prove
  production publication, published sign-in or restoration of production data.
- The money-storage work passed 227 tests, including required browser tests and
  a disposable real PostgreSQL instance. This is the recorded result for that
  change, not a claim of a new full-suite run after subsequent merges.
  Two existing test-library deprecation warnings remain.
- Real PostgreSQL tests exercised the old integer boundary, applicable schema
  maximums, negative opening balances, corrections, exports, and safe rollback.
- Database-native SQLite and PostgreSQL backup/restore rehearsals were added
  and passed with synthetic data; see docs/BACKUP_RESTORE.md. They are not
  automated off-host backups of the running app.
- The prepublish script now requires PostgreSQL and browser checks on disposable
  databases. It does not migrate the caller's database or prove live sign-in.
- Isolated temporary SQLite database: migrations and startup succeeded without
  Replit or Clerk environment variables. Sign-in page returned 200; protected
  pages redirected (307); financial APIs denied access (401).
- 50 local TestClient calls to the public auth-config endpoint measured
  median 2.13 ms, maximum 4.20 ms. This is a small smoke measurement, NOT a
  load test, production benchmark, or measurement of real Clerk latency.
- Development web workflow restarted successfully.
- No independent external-host deployment or production user sign-in was
  established by these tests.

## Profit Engine scope

**Phase 2 design approved September 29, 2026; only the organizational first
slice was subsequently authorized to begin:** See
[PORTFOLIO_PHASE2_SCOPE.md](PORTFOLIO_PHASE2_SCOPE.md) for authoritative approved
boundaries, sample reconciliations and the isolated testing plan. Phase 2a
portfolios and one unique existing Account link per container organize records
only. An Account link is immutable after creation; portfolio membership can
be changed without moving money. Archiving a portfolio with active containers
is blocked rather than cascading. Opening snapshots, reconciliation/conversion
and weighted-average stock/ETF activity remain approved *design*, not
implemented behavior. Existing account balance semantics remain unresolved:
do not assume cash-only balances or no records. Actual conversion, overlap
corrections, deletion, source push and publication require separate approval.

Read [PROFIT_ENGINE_REVIEW.md](PROFIT_ENGINE_REVIEW.md) for implemented Phase 1,
the organization-only Phase 2a slice, and later proposals. Holdings and
investment activity, transfers, market analysis, trading plans/fills, journals,
attention and analytics remain unimplemented. The approved Phase 2 design
settles the target account/container relationship and valuation policy, **not**
the meaning of any existing balance. Each affected account and investment
still needs reconciliation and execution approval before any valuation switch.
Historical investments remain unchanged. Source synchronization, production
publication and live sign-in are separate checks; do not infer them from
implementation or local tests.

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
audited old-to-new **auth identity mapping** onto the existing Serenity
workspaces. Financial workspace IDs need not change. Do not automatically link
identity by matching email. Keep a rollback backup.

The application is not yet proven on an owned server. Its database backup/restore
and authentication migration procedures must be rehearsed before a real move.
Do not change managed keys now or weaken authentication to make migration easier.

## New requirements for brainstorming — NOT implemented

### Profile and sign-in settings

- Add a Settings/Profile page where a signed-in user can manage their login
  email and password, using the authentication provider's supported secure flows.
- Require appropriate recent authentication for sensitive changes, verify a
  new email before activation, and define lost-password/account-recovery behavior.
- An email/password change must preserve the same Serenity user and workspace;
  never create a second workspace or transfer records based on an email match.
- Check actual managed-provider capabilities before selecting UI or building
  custom credential handling. Do not store passwords in Serenity's financial DB.
- Test cancellation, duplicate/unverified email, failed verification, expired
  sessions, recovery, and session invalidation after credential changes.

### Invitation-only users and strict privacy

- Allow selected users to access the app, each with only their own financial data.
- Existing workspace-scoped backend authorization is the foundation, not a
  future optional feature. Preserve isolation on every read, write, correction,
  dashboard, export and newly added endpoint.
- Invitation-only operation is the intended policy; do not assume the sign-in
  page's invitation wording proves that provider registration is restricted.
  Verify the actual production policy before inviting users.
- Invitations grant entry, not access to the inviter's workspace. Being an
  app administrator must not implicitly grant browsing of another user's finances.
- Define invitation acceptance, expiry/revocation, deactivation/reactivation,
  and account recovery before implementing an invitation-management screen.
- Shared households, shared workspaces and cross-user financial views are NOT
  requested. Do not add them implicitly.

### Six-digit PIN after initial setup

Requested outcome: after creating an account, a user can return using a
six-digit PIN. No PIN enrollment, verification or unlock feature exists yet.

A six-digit PIN has only one million possibilities. It should not simply
replace the existing internet-facing password/Clerk authentication with an
unrestricted reusable secret.

Recommended design to explore: opt-in trusted-device quick unlock after full
sign-in, backed by a valid provider session and device-bound proof. Prefer a
passkey/device-authenticator design where feasible. A device PIN used by an
authenticator is not necessarily an app-chosen six-digit PIN; clarify that UX
before claiming it meets the requirement. A cosmetic browser lock is not
server-side access control.

If an app-managed PIN is required, design secure server-side credential
verification, strong hashing, per-account/device attempt limits, cooldowns,
device enrollment/revocation, short session lifetimes, and lost-device/PIN
recovery. Do not save a plaintext PIN, auth token, or financial draft in
localStorage. Never bypass Clerk revocation, inactive-user checks, workspace
authorization or full reauthentication for email/password changes.

Brainstorming decisions: PIN on trusted devices only versus login anywhere;
how the account is identified; shared-device behavior; inactivity timeout;
device revocation; and when full sign-in is mandatory. These choices are still
open and need a security review before implementation.

## Suggested brainstorming priorities

1. Profile/settings and invitation lifecycle, preserving private workspaces.
2. Backup reliability: automated encrypted backups and a tested restore procedure.
3. Daily workflow: income plans versus actual deposits, transaction entry and corrections.
4. Reporting priorities: cash flow, bill planning and actionable summaries.
5. Secure quick unlock: choose the PIN/trusted-device model before implementation.
6. Future hosting: choose a target server and identity-provider ownership plan
   before attempting migration.

## Instructions for the next chat

Help brainstorm from this baseline; do not rebuild or replace the app by default.
Separate confirmed features from proposals. Preserve ownership isolation,
cryptographic authentication, accurate financial arithmetic and existing records.
Inspect the latest code/tests before making changes. Do not assume GitHub includes
database contents, secrets, Clerk users or a running deployment.

Suggested opening prompt:

> Review this Serenity handoff and help plan profile settings, invitation-only
> user access, strict financial-data privacy, and secure six-digit PIN quick
> access. Separate existing capabilities from missing work. Recommend incremental
> changes to the current identity/workspace model, identify security tradeoffs,
> and outline acceptance tests. We are not preparing a public launch yet.
