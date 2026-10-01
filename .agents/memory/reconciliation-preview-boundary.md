---
name: Reconciliation preview boundary
description: Why reconciliation reports are disposable evidence rather than conversion authorizations.
---

Keep reconciliation previews disposable and separate from any future conversion approval.

**Why:** Read-only preview authorization does not authorize storing conversion state, adjusting cash, or changing valuation eligibility. Signed evidence can establish what was reviewed, but cannot itself authorize execution. Legacy investments have no account relationship, so account completeness is a user attestation, not an inferred fact.

**How to apply:** Future execution needs a separately approved design for durable approval, backup gating, atomic non-income corrections, idempotency, and rollback. Revalidate all dependencies at execution; do not treat a current preview token as an approval or silently persist draft mappings.

Use immutable approved report evidence for execution, and keep a non-income
cash correction distinct from Income/Expense transaction history. Reversal
checks the committed post-conversion state, not the pre-conversion fingerprint.

**Why:** Conversion changes the source fingerprint itself; comparing reversal
to the original preview would reject every valid reversal. Encoding overlap as
ordinary income or expense would misstate financial history.

**How to apply:** When building the execution slice, serialize same-owner
financial writers and compare exact component totals inside the transaction;
make reversal append a compensating entry only when no dependent activity exists.