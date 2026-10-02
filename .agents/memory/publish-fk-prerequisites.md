---
name: Publish FK prerequisites
description: Composite owner keys and independent validation of the managed Publish schema diff.
---

Declare owner-matched foreign-key targets as actual unique constraints, not
only standalone unique indexes, when they must travel through managed Publish.
Validate the generated Publish plan independently of Alembic.

**Why:** On 2026-10-01, development accepted owner-matched foreign keys using
valid standalone composite unique indexes. The generated Publish diff omitted
those parent indexes. Adding real constraints made the keys visible, but the
recomputed diff still placed constraints on existing tables after foreign keys
that referenced them. The exact sequence failed in isolated PostgreSQL; the
same statements with the prerequisite constraints first succeeded.

**How to apply:** Inspect both database catalogs and the freshly generated
Publish statements. Check that every referenced composite key exists before
its foreign key is created. Do not infer Publish success from a passing
Alembic upgrade or from an absence of destructive-change warnings. Re-check
current behavior rather than assuming the observed ordering persists.
Never bypass Publish with production DDL or deployment/startup migration hooks,
and do not remove ownership protections merely to make validation pass.

A Publish comparison can propose dropping legacy standalone unique indexes
even when those indexes still exist in both catalogs after FK restoration.

**Why:** Restored development FKs bound to legacy indexes, while the published
schema had the same indexes without FK dependencies; the generated comparison
proposed four removals despite their continued physical presence in development.

**How to apply:** Inspect actual index definitions and FK `conindid` bindings,
verify replacement true unique constraints in production, and replay the exact
generated sequence. Treat unexpected index removals as an owner-review boundary,
not as proof that development lacks the indexes or as an automatic safe change.