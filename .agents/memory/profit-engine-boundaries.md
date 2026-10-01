---
name: Profit Engine boundaries
description: Why Profit Engine work is incremental and must preserve existing valuation and historical reference meaning.
---

Treat the Profit Engine handoff as a staged expansion, not permission to replace existing financial records. Begin with the mathematical/reference foundation, then resolve portfolio/account valuation and legacy conversion decisions before migrating holdings.

**Why:** Existing investments are starting-position snapshots without enough acquisition history to invent transactions or cost-basis lots. Treating brokerage cash and positions as additional assets without reconciliation can double-count net worth.

**How to apply:** Require an explicit, tested reconciliation for future investment conversion. Hypothetical calculator outputs must not post income or change account balances. USD-only reference calculations do not establish multicurrency support or verified exchange data.

The owner approved Phase 2 design boundaries on September 29, 2026, then
authorized organization-only portfolios and linked containers. Neither approval
authorizes investment conversion or a valuation switch. Consult
docs/PORTFOLIO_PHASE2_SCOPE.md before extending portfolios or activity; do not
repeat settled design questions.

**Why:** The owner's answer about existing account balances was deliberately
non-specific (mixed, unsure, or no records). It establishes uncertainty, not
cash-only semantics or an empty dataset. Design approval cannot resolve facts
about individual records.

**How to apply:** Preserve the distinction between approved target policy and
per-record execution approval. An overlap correction can legitimately change
net worth, but only with an explained, separately approved reconciliation.

Archived reference specifications must remain available for historical reproduction; archiving a symbol is not revocation of access to its own historical mathematics.

**Why:** A later specification edit or archive must not rewrite the meaning of earlier calculations. This differs from permanent removal of standalone bills, debts, and legacy investment records.

**How to apply:** Keep historical specification ownership checks intact, bind future execution facts to a specific version, and distinguish calculator output from actual trading records.

Lifecycle checks involving editable parent membership must lock and refresh the
child before resolving and locking its parent.

**Why:** Locking only the previously read parent does not prevent a simultaneous
move from making an activation check apply to the wrong group.

**How to apply:** For lifecycle or membership writes, serialize child changes
first, then check the current parent under its own lock. Exercise stale
identity-map reads in disposable PostgreSQL concurrency tests.

New investments entered through the portfolio assignment flow remain uncounted
until the owner reviews the account balance; existing investment records must
not be silently reclassified. A portfolio is the direct organizational home
for investments; an Account link is not required at entry.

**Why:** The owner explicitly chose draft-first entry after learning that an
account balance can already contain the security's value, then confirmed that
portfolio-first entry should not require an Account/container. Neither a
portfolio choice nor an account link proves a value belongs in net worth.

**How to apply:** Keep portfolio membership distinct from cash-account
reconciliation. Treat draft assignment as a review hint, not a posting or
approval. Organizing an existing counted investment into a portfolio must not
reclassify it or change totals. Preserve old links rather than deleting
historical information.
Cash-only review may yield a genuine positive delta; combined-balance review
needs evidence and an offset. Do not assume all conversions are zero-delta.