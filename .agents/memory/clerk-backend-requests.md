---
name: Clerk backend request filtering
description: Distinguish upstream request filtering from rejected accounts during Python authentication troubleshooting.
---

Check transport-level rejection before blaming invitations, credentials, or user registration.

**Why:** On 2026-09-23, the same read-only Clerk API call with the same configured credential returned a non-JSON 403 using Python urllib's default User-Agent and 200 with an explicit application User-Agent. Serenity had converted this upstream failure into a generic sign-in 401.

**How to apply:** Use an explicit application User-Agent for backend Clerk requests. Diagnose with HTTP status and response format only; never log credentials, tokens, session identifiers, or user data. Do not change Clerk keys or invite rules based solely on a generic application 401.