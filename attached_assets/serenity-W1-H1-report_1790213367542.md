# Serenity W1 + H1: report and apply steps (2026-09-24)

Apply **W1, then H1**, one commit each. Tests were **not run** in Claude's sandbox (PyPI is
blocked there); every file compiles. **Replit's `prepublish_check.sh` is the authoritative
test run.** Please paste the test count and any failures back.

## W1: internal identity and workspaces (migration 0011)

**What changes:** a verified Clerk login now maps to Serenity's own user and workspace, and
every financial record's `owner_id` holds the **workspace id** instead of the Clerk id.
Read `docs/identity.md` for the full explanation.

| File | Change |
|---|---|
| `models/identity.py` | **new**: `users`, `workspaces`, `auth_identities` |
| `services/identity_service.py` | **new**: look up or provision the workspace; deactivate/reactivate users |
| `migrations/versions/0011_identity_and_workspaces.py` | **new**: tables + moves existing dev owners into workspaces; reversible |
| `auth.py` | `require_session`/`require_page_session` return the workspace id; 403 for deactivated users, 503 if Clerk isn't configured; `next=` is URL-encoded; comments restored |
| `main.py` | sign-in (`POST /auth/session`) provisions the workspace and records `last_sign_in_at`; `/auth/me` fixed |
| `services/ownership.py` | docstring: "owner" now means workspace |
| `migrations/env.py` | imports the identity models |
| `scripts/check_production_rows.py` | also reports rows **not linked to a workspace** |
| `tests/conftest.py` | imports identity models; `real_auth_client` sets a test Clerk key |
| `tests/test_identity.py` | **new**: provisioning, isolation, issuer separation, duplicates, deactivation, missing config, sign-in stamp |
| `tests/test_migrations.py` | 0008 backfill test now stops at 0008; four new 0011 tests |
| `tests/test_auth.py` | redirect test expects the encoded `next` |
| `tests/test_workspace_check.py` | **new**: the orphaned-row check |
| `docs/identity.md` | **new** |

**Plus one command** (renames the misleading `user_id` variable in routes to `owner_id`;
I read every file in `api/` and it's only ever the `require_session` value):

```bash
sed -i 's/\buser_id\b/owner_id/g' api/*.py
grep -n "user_id" api/*.py     # should print nothing
```

**Deliberate choices:** `owner_id` keeps its column name (a rename could be applied by
Publish as drop+add), and there are no database foreign keys to `workspaces` (SQLite's
table rebuild would drop the business/dependent name indexes). Both are explained in
`docs/identity.md`.

## H1: fixes (migration 0012)

| File | Change |
|---|---|
| `models/investment.py` | `quantity_units` → `BigInteger` |
| `migrations/versions/0012_investment_quantity_bigint.py` | **new**: widens the column on Postgres; no-op on SQLite |
| `schemas/finance.py` | quantity capped at 1,000,000,000 |
| `tests/test_investment_quantity.py` | **new** |

**Why:** a 32-bit column at 100,000,000 units per share overflows above **~21.47 shares**
on PostgreSQL. SQLite hid it. Fix this before entering real investments.

**Plus:** `git rm SERENITY_README.md`

**Clerk version pin (manual; I won't guess a version).** `frontend/static/js/auth.js` loads
`@clerk/clerk-js@latest` next to a pinned `@clerk/ui@1.34.0`. To pin:
1. Open `https://cdn.jsdelivr.net/npm/@clerk/clerk-js@latest/package.json` and note `"version"`.
2. Replace `@latest` in `clerkScriptUrl` with `@<that version>`.
3. Sign in and out on the preview. If it works, commit. If sign-in breaks, revert.

**Dropped from H1 (and why):**
- Deleting `artifacts/`: `artifacts/serenity/.replit-artifact/artifact.toml` is the
  **live production run command**. Leave it. Cleaning the other two artifact folders
  should be done through Replit, not by deleting files.
- CSV guard: it already strips whitespace before checking, so it's fine.

## Apply steps

For each package in order (W1, then H1):

1. Unzip over your local clone. For W1, also run the `sed` command above.
   For H1, also run `git rm SERENITY_README.md`.
2. Commit and push.
3. In Replit: `git pull`.
4. **W1 only:** run the migration **in the Replit Shell** (so `CLERK_PUBLISHABLE_KEY` is
   set and your dev test data stays reachable):
   ```bash
   alembic upgrade head
   ```
5. `SERENITY_DEVELOPMENT_DATABASE=1 bash scripts/prepublish_check.sh`
6. After both packages pass, before publishing:
   ```bash
   SERENITY_CHECK_DATABASE_URL="<production url>" python scripts/check_production_rows.py
   ```
   Expect `RESULT: no financial rows.` If it says anything else, stop and send me the output.
7. Publish. Replit will show schema changes: **three new tables** and **one column type
   change** (`investments.quantity_units` → bigint). No drops. If it proposes dropping
   anything, cancel and send me a screenshot.
8. Run the Clerk smoke test from `docs/security.md`, then in the Clerk dashboard confirm
   sign-up is **Restricted**.
9. Start entering your real data.

**Suggested commit messages**
- W1: `Identity: internal users, auth identities and workspaces (0011); records owned by workspace; encoded sign-in next; docs/identity.md`
- H1: `Fix investment quantity overflow (0012 BigInteger, 1B cap); remove duplicate README`

## Risks I couldn't rule out without running tests

- A test I didn't read (e.g. `test_export.py`, `test_business_dependents.py`) may compare
  a stored `owner_id` to a Clerk id under `real_auth_client`. The fix would be to compare
  against the workspace. I read `test_auth`, `test_clerk_handoff`, `test_owner_isolation`,
  `test_migrations` and `test_production_check`, which are the most likely ones.
- `tests/test_identity.py` imports the `clerk` fixture from `test_clerk_handoff.py`. That's
  standard pytest, but if collection complains, move the fixture into `conftest.py`.
- Money columns are still 32-bit (about $21.4M max per value) while the validator allows
  up to $1T. Larger values would error on Postgres. It's unlikely for personal use; tell me
  if you want them widened while production is still empty.

## Deferred

Profile page (W2), Goals, restore, passkeys/PIN, provider-linking tool, self-hosting.
