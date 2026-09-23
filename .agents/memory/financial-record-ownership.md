---
name: Financial record ownership
description: The privacy boundary for Serenity financial data and legacy database migration.
---

Serenity uses per-user ownership, not a shared household dataset. The authenticated Clerk user ID is the owner for accounts, transactions, transaction corrections, finance records, business/dependent labels, summaries, and exports. Cross-record links must resolve to the same owner.

**Why:** Invite-only access controls entry but does not separate invited members. A default or guessed owner during migration could expose existing financial data to the wrong member.

**How to apply:** Pass the authenticated user ID through every protected API into service queries and mutations. When migrating populated legacy data, require `SERENITY_LEGACY_OWNER_ID`; never silently assign a default owner.