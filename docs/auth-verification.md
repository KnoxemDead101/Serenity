# Clerk token verification

Serenity uses PyJWT with cryptography to verify RS256 Clerk session tokens.
The issuer and JWKS URL are derived only from the configured managed
`CLERK_PUBLISHABLE_KEY`, not token claims or request headers. Managed keys must
not be replaced. JWKS are cached for five minutes and refreshed for key
rotation by PyJWT. Network or verification failures deny the exchange.

The browser handoff requires issuer, expiry, not-before, issued-at, subject,
session ID, and an authorized-party (`azp`) origin. Signature and claims are
checked before the live Clerk session lookup. That lookup additionally
requires an active session belonging to the verified subject.

## Allowed browser origins

Set `SERENITY_AUTHORIZED_PARTIES` to a comma-separated list of exact trusted
browser origins (scheme, hostname, and port if non-default; no trailing slash).
For example, a local server can use `http://localhost:5000`.
Do not use wildcards or take this list from HTTP headers.

In development (`SERENITY_DEV=1`), the configured Replit development domains
are also allowed as HTTPS origins. In production, explicitly configure the
actual published/custom origin in `SERENITY_AUTHORIZED_PARTIES` before enabling
sign-in. Do not assume a development domain is the published domain. An empty
production allowlist intentionally rejects all handoffs.

## Deployment readiness

Confirm the primary URL and any custom URLs from the deployment service, never
from `REPLIT_DOMAINS` or `REPLIT_DEV_DOMAIN`. Set the production-only
`SERENITY_AUTHORIZED_PARTIES` to the exact origins actually used for sign-in.
Keep managed Clerk keys unchanged and keep `SERENITY_DEV` disabled in production.

Run `python scripts/check_production_auth.py` with the production configuration
and `SERENITY_CHECK_PUBLISHED_ORIGIN` set to the independently confirmed origin.
This offline check exits nonzero for missing/mismatched origins, preview domains,
HTTP, wildcard origins, URL credentials, paths, queries, fragments, and empty list
entries. HTTPS origins must use canonical lowercase DNS names and omit port 443.
Additional custom origins can be comma-separated; verify each sign-in origin
by rerunning with that origin as `SERENITY_CHECK_PUBLISHED_ORIGIN`.
Neither checker prints the configured origin values or Clerk keys.

The existing `python scripts/check_production_rows.py` now requires this same
origin check as well as the read-only ownership report. It still requires an
explicit `SERENITY_CHECK_DATABASE_URL`; an empty database does not bypass the
origin check. Run against the intended environment, not the development defaults.

A passing configuration check is **not** proof of working sign-in. After
publishing configuration changes, use the actual published/custom origin:

1. Pass any Replit private-deployment access gate with an authorized account.
2. Open Serenity sign-in and confirm the managed Clerk UI loads.
3. Complete sign-in with a production test account, confirm the session handoff
   succeeds and an authenticated financial page loads without entering records.
4. Refresh to confirm the session persists, then sign out and confirm protected
   pages no longer allow access.
5. Record only the origin, date, and pass/fail result, never credentials, tokens,
   cookies, or financial contents. Repeat for each supported custom origin.

On 2026-09-23 the deployment service confirmed
`https://serenity--lknox3.replit.app` with no additional URLs and private
visibility. An unauthenticated live browser check reached the Replit access
gate, not Serenity. End-to-end managed Clerk sign-in remains unverified; do
not enter real financial records until that verification is complete.

Serenity's signed, HTTP-only cookie binds to the verified Clerk session and
owner and lasts up to 12 hours. Every protected request checks that exact
session remains active and owned by that user, failing closed on Clerk outages.
Moving off Replit-managed Clerk requires a new, independently supported Clerk
instance and explicit verified user-ID ownership migration; see
`docs/HOSTING.md`. Matching emails alone is not safe.