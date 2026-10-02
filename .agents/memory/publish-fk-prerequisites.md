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