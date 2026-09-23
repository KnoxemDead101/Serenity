---
name: Clerk token trust
description: Trust boundaries for the Python browser-to-session exchange.
---

Keep trusted JWT issuers and browser origin allowlists independent of caller-controlled claims and HTTP headers.

**Why:** An active Clerk session lookup proves only that a session exists, not that the caller possesses a signed token. Origin headers and Host headers are also not configuration. The browser-only exchange deliberately requires an authorized party even when a generic Clerk token verifier might allow its absence.

**How to apply:** Preserve cryptographic verification before session lookup and keep the production origin list explicit. Do not derive production origins from development-domain environment variables. Treat a missing trust configuration as a denial, not an invitation to weaken checks.