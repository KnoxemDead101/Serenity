---
name: Financial record ownership
description: The privacy boundary for Serenity financial data and legacy database migration.
---

Serenity uses isolated ownership, not a shared household dataset. Provider changes must preserve financial ownership through explicit verified identity linking, never guessed links based on email or matching subject strings.

**Why:** Invite-only access controls entry but does not separate invited members. A default or guessed owner during migration could expose existing financial data to the wrong member.

**How to apply:** Resolve the verified provider, issuer and subject to the existing internal workspace. Never trust a caller-selected workspace without authorization. For legacy ownership migration, confirm tenant provenance before changing rows; mixed or uncertain tenants require an explicit mapping, not an automatic backfill.

## Prove enforcement under runtime settings

Constraint tests must cover the application's actual connection policy, not
only a stronger test-only configuration. A declared foreign key is not proof
that every supported runtime enforces it.

**Why:** A private SQLite fixture with foreign keys explicitly enabled proved
the relationship definition but did not prove protection under Serenity's
default legacy SQLite connection policy. That distinction matters for owner
matching and preventing orphaned planning data.

**How to apply:** Exercise raw ownership-changing writes and parent deletion
under default SQLite settings as well as explicit FK-enabled fixtures and
disposable PostgreSQL. Do not silently change shared financial behavior to
make a new domain's integrity tests pass.