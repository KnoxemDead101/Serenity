# Hosting Serenity outside Replit

Serenity is a FastAPI/SQLAlchemy application, not tied to a Replit runtime.
Python 3.11, the files in this repository, `pip install -r requirements.txt`,
outbound HTTPS to Clerk and its SDK CDN, and a persistent database are needed.
Replit-specific `.replit` and publishing workflows are not needed on another
Linux host. This is an operator checklist, **not** a tested external deployment.

## Before moving data or enabling sign-in

1. Choose a domain with HTTPS and a persistent database. PostgreSQL with a
   dedicated database and backups is recommended. SQLite is supported for a
   single-instance deployment only: use an **absolute path** on a persistent
   backed-up volume, not `sqlite:///./serenity.db` on ephemeral storage. Do
   not run multiple application replicas against a SQLite file.
2. Set `DATABASE_URL` to the intended database (`postgresql://...` and
   `postgres://...` are normalized to psycopg). Keep credentials in your host's
   secrets manager. The app's database engine is initialized at import time,
   so restart processes after changing `DATABASE_URL`.
3. Set a long random `SESSION_SECRET`, and keep it consistent across processes
   and restarts. Changing it invalidates every signed Serenity cookie.
4. Set `CLERK_PUBLISHABLE_KEY` and `CLERK_SECRET_KEY` for the **same** Clerk
   instance and set `SERENITY_AUTHORIZED_PARTIES` to the exact HTTPS origin(s)
   where users sign in (comma-separated, including nondefault ports). Never
   construct the allowlist from incoming headers. `SERENITY_DEV` must be unset
   in production (it enables insecure cookies and preview-origin handling).
   **Hosting migration blocker:** Replit's managed Clerk tenant cannot be
   exported to an independent host. Set up a separately supported Clerk
   instance before an external deployment. Financial rows are owned by
   Serenity workspace IDs after migration 0011. To retain existing users'
   access, migrate the **auth identity mappings** from the old Clerk issuer
   and subject to independently verified new provider identities, with
   account-owner consent, an audited mapping and a rollback backup. Do not
   reassign a workspace by matching email addresses. Do not expose existing
   financial data on the new host until identity mapping is verified.
   Browser sign-in also depends on `@clerk/ui` and `@clerk/clerk-js`
   browser scripts loaded from jsDelivr by `frontend/static/js/auth.js`.
5. Keep all secrets and DB files out of source control and logs. `.env.example`
   describes variables; the app does **not** automatically read `.env`.

## Deploy (from the project root)

Install Python 3.11 and dependencies in an isolated environment using
`python -m pip install -r requirements.txt`. Install and configure a database
separately. **Back up the database before each upgrade**; stop writers or use a
database-consistent snapshot. With production `DATABASE_URL` configured:

```sh
alembic upgrade head
alembic current
uvicorn main:app --host 127.0.0.1 --port 8000
```

The migrations are **not** applied by application startup; do not expose the
new version before its migrations finish. Run the process under a supervisor
(for example systemd) and terminate cleanly on deployment. Put an HTTPS
reverse proxy (for example Caddy or nginx) in front of the loopback listener,
forward the original host, and do not serve HTTP to browsers: Serenity's
production session cookie is Secure and HttpOnly. Set TLS, firewall rules,
monitoring, and a backup/restore schedule on the host. Avoid reverse-proxy
header trust for untrusted clients; only configure forwarded headers for your
own proxy. The default `/docs` is public API documentation; limit access at
the proxy if exposing that metadata is inappropriate for your deployment.

Before applying migration 0011 to a database with pre-existing financial
records, inspect every distinct owner ID and establish that each is a subject
of the exact configured Clerk issuer. Back up and verify restore first. Only
then set `SERENITY_LEGACY_CLERK_ISSUER` to that exact HTTPS issuer for the
migration; without it migration aborts before altering schema or rows. If
owners have mixed or unknown origins, do not set it or run the migration;
prepare an individually audited mapping instead. This setting is **not**
needed for an empty database. See `docs/identity.md`. Check for orphan
workspace owners before publishing. Downgrades involving populated identity
tables require an explicit backup and confirmation and reject ambiguous
identity mappings; restoring a verified backup is safer.

Run `SERENITY_CHECK_PUBLISHED_ORIGIN=https://your-real-app.example
python scripts/check_production_auth.py` with the configured origin and
`SERENITY_AUTHORIZED_PARTIES` before opening access. This checks configuration,
not live sign-in. Complete a real production sign-in, authenticated read,
refresh, sign-out, and unauthorized access check before entering actual
financial records. See `docs/auth-verification.md`.

## Recovery, backups, and limitations

See [the database-native backup/restore rehearsal](BACKUP_RESTORE.md) for
repeatable disposable SQLite and PostgreSQL checks and the isolated-destination
operator recovery procedure. Run it before relying on backups; JSON/CSV exports
are not a substitute.

- Take encrypted, tested database backups; restore into an isolated database
  first and check migrations and owner-scoped records. JSON/CSV export is **not**
  a database restore mechanism. Never overwrite a populated production
  database with the development SQLite file.
- The rehearsal provisions only disposable databases. The app does not include
  production database provisioning, scheduled encrypted backups, automated
  production recovery, or automatic identity-mapping migration between Clerk tenants.
  PostgreSQL migrations have been designed through Alembic, but external-host
  runtime, TLS and independent Clerk sign-in are not proven by local tests.
  Test on the intended server before relying on it.
- Every protected request validates its bound session through Clerk's Backend
  API (8-second network timeout). An outage **denies access**, including
  exports; it does not delete stored data. Monitor Clerk/API availability and
  expect this network dependency to affect request latency and throughput.
- Run `SERENITY_REQUIRE_BROWSER=1 pytest -q` before deploying; Chromium and
  Playwright are needed for the browser tests. Do not copy the test database to
  production. Test with an empty isolated database and no Replit variables to
  check core portability; that test cannot establish working production Clerk.
