# Internal identities and workspace ownership

Financial `owner_id` is the ID of a Serenity workspace, not a Clerk user.
On a verified sign-in, the provider + configured issuer + subject identifies
one Serenity user and their primary workspace. A user has one primary
workspace today. No email is used to join identities or transfer ownership.
Clerk's RSA token and live session are checked before this lookup. An inactive
Serenity user receives a 403 with `X-Serenity-Account-Status: inactive`
on pages, APIs, exports and session exchange; no new cookie is issued.
Unconfigured or unavailable Clerk returns 503; revoked credentials return 401.

`users`, `workspaces` and `auth_identities` are created by Alembic migration
0011. Services and authorization use workspace IDs throughout. Financial
columns retain the name `owner_id` to avoid a potentially destructive rename.
There are deliberately no financial-table foreign keys to workspaces because
SQLite table rebuilds would drop existing expression indexes. The read-only
`scripts/check_production_rows.py` reports owners not linked to a workspace and
fails publishing checks on any orphan.

**Populated legacy database migration is sensitive.** 0011 refuses to proceed
if it finds financial records and `SERENITY_LEGACY_CLERK_ISSUER` is missing,
malformed or differs from the issuer derived from `CLERK_PUBLISHABLE_KEY`.
Before setting it, the operator must take and verify a database backup and
independently confirm that **every** old financial owner ID belongs to that
exact tenant. The configured key alone does not prove this. If data mixes
tenants, import histories or other owner formats, do not run 0011: a
per-owner audited identity mapping is necessary. Empty databases migrate
normally without this setting. Never link by email.

Downgrades with identities require a separate verified backup and
`SERENITY_CONFIRM_WORKSPACE_DOWNGRADE=1`. Downgrade refuses missing or multiple
identities, duplicate issuer/subject mappings, orphan owners, or issuer
mismatch for financial rows; in these situations restore the backup instead.
An automatic downgrade is not an identity migration strategy.

Do not apply this migration to a real database without reviewing its row
counts, issuer provenance, backup and intended publish schema changes. Replit
Publish's schema comparison and external-host Alembic upgrades are different
operations; see `docs/HOSTING.md`. Replit-managed Clerk tenants are not
exportable, so a future authentication-provider change needs an independently
verified and audited user-ID mapping, not an email match.