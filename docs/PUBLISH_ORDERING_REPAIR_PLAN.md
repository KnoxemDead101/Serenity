# Guarded Publish-order repair — owner approved

The owner explicitly approved this guarded repair on 2026-10-01. Only the
development staging changes are authorized; the owner performs both Publishes.
The corrected development schema already includes real composite unique
constraints. The generated Publish diff still creates dependent foreign keys
before adding four prerequisite constraints on existing production tables.
An isolated PostgreSQL replay confirms the failure and a constraints-first
control succeeds. Passing Alembic tests does not resolve that Publish ordering.

## Preferred outcome

The Publish flow generates and validates a constraints-first migration, without
temporary removal of ownership safeguards. No production DDL may be applied by
the agent, and no deployment/startup mutation hook may be added.

## Approved staged workaround

1. Add a fail-closed write gate for affected financial features. It must block
   affected application/service writes while required ownership foreign keys
   are absent, show a clear temporary-unavailable state, and preserve
   authentication and owner-scoped reads. Confirm every affected write path.
2. In development only, use a forward Alembic migration to temporarily remove
   the seven foreign keys whose targets are the four existing parent tables:
   - `fk_opening_positions_owner_account`
   - `fk_opening_positions_owner_source`
   - `fk_opening_positions_owner_instrument`
   - `fk_opening_positions_owner_specification`
   - `fk_investment_accounts_owner_account`
   - `fk_cash_reconciliation_entries_owner_account`
   - `fk_valuation_eligibility_owner_source`
   Preserve every row, financial value, unique key, and other foreign key.
   Retain canonical definitions needed for restoration.
3. Recompute the exact Publish diff, replay it on an isolated synthetic
   production-shaped schema, and run regressions plus write-gate failure tests.
   Stop if any unanticipated drop, data loss, or unguarded write appears.
4. Ask the owner to authorize and perform the first Publish. The new financial
   features remain write-blocked. Verify the four production parent constraints
   through read-only queries; do not assume a successful build proves the schema.
5. Restore all seven foreign keys in development with a forward migration.
   Recompute/replay the second Publish diff and run tests. The write gate must
   stay closed until the actual database has every required ownership safeguard.
6. Ask the owner to authorize and perform the second Publish. Verify all
   required production constraints through read-only queries before writes
   become available. Resume the approved Serenity Next baseline/trust program.

No records are deleted or overwritten. Nevertheless, temporary removal of
ownership constraints is a material/destructive schema decision requiring
explicit owner review; broad arc authorization alone does not approve it.
Do not perform these steps if the write gate cannot cover every affected path.

## First-release staging

Development staging is applied. Record digests and counts matched before and
after across 15 inspected owner-scoped tables, including every affected parent
and child and the Goals tables; no record values were logged. SQLite
retains its existing foreign keys and is not the managed Publish source.

The staged application protects financial/planning API writes, direct
owner-scoped ORM flushes, and typed bulk mutations. Sign-in and reads remain
available. The UI shows the read-only state and refuses ordinary saves.
Unknown schema health fails closed. Constraint verification checks table,
columns, parent, delete policy, and validation status; matching names alone are
not sufficient. Transaction-held read locks prevent concurrent FK removal
between a successful safety check and application DML.

The captured first-Publish schema plan is
`tests/fixtures/publish_stage1_schema_diff.json`. It contains 58 statements,
no structural-data-loss flag, and no warnings. An isolated test applies it
exactly in generated order to the historical production-shaped schema and
checks prior record preservation, parent-key creation, and write refusal.
This fixture is test evidence, never a production migration script.

**Next release boundary:** the owner performs the first Publish. Verify the
four parent constraints through read-only production queries before preparing
the second release. Do not restore development FKs early: doing so would put
the original ordering failure back into the first Publish plan.

The full required prepublish gate completed on 2026-10-02: **814 passed,
0 failed, 2 skipped**. The skips are the existing optional restore and separate
conversion-lock checks. PostgreSQL staging/restoration, exact generated-SQL
replay, API/service/bulk refusal, wrong/unvalidated FK refusal, and synthetic
signed-in browser behavior passed. The managed Serenity preview restarted
successfully; its unauthenticated sign-in page was visually verified.
Actual published sign-in remains the separate existing verification item.

## Second-release preparation (2026-10-02)

A fresh schema-only production replica query confirmed all four prerequisite
parent unique constraints, including exact columns and validated status.
The seven staged ownership foreign keys remain absent in production. Deployment
metadata reports an active successful private publication; build success alone
is not evidence of restored ownership protections.

Forward development migration `0024_restore_publish_keys` restored all seven
references. Before/after server-side record digests and counts matched across
**all 22 owner-scoped tables**. No individual records, identities, values, or
financial totals were returned. Development write safety now reports `NORMAL`;
production restoration has not been performed. Downgrading this revision keeps
the restored references rather than silently removing ownership protection.

The fresh second-release comparison is captured in
`tests/fixtures/publish_stage2_schema_diff.json`: **12 statements**, no warnings,
no structural-data-loss flag, and no dropped/truncated tables or columns:

- Four `DROP INDEX` statements for redundant standalone `ux_*` parent indexes.
- Seven ownership foreign-key additions.
- The separately merged `ck_goals_manual_progress_only` check.

The four legacy indexes exist in both database catalogs. In development the
restored foreign keys bind to them; in production no foreign keys currently
depend on those four indexes. The actual comparison nevertheless proposes their
removal. Each matching true `uq_*` unique constraint was independently confirmed
in production and remains in the generated plan. Exact-order isolated replay
passes, preserves prior account/Goal rows, and proves all seven new references
bind to true parent unique constraints afterward.

**Required review before the second Publish:** these index removals were not
part of the original seven-key staging approval. Obtain explicit owner review
of the four redundant index removals. The bundled Goal check also requires
renewed permission for the documented production aggregate-only preflight;
the earlier zero counts are not a current rollout preflight. Do not retrieve
record details, silently correct records, or infer authorization from a task
being queued. If unsupported Goals exist, stop and preserve them.

After this review, a passing full publishing gate, and the owner's second
Publish, verify every restored production FK definition and validated status
through read-only queries. Only then declare the repair complete and begin the
approved Serenity Next trust/personal-operating-system waves without routine
slice re-authorization.

The second-release full required gate passed on 2026-10-02: **951 passed,
0 failed, 2 skipped**. The exact first/second Publish replay, forward
restoration, historical downgrade preservation, direct database Goal guards,
and required PostgreSQL/browser checks passed. A duplicate root app workflow
was removed after it conflicted with the managed artifact's port; Run now
targets the managed Serenity service. That service is running and the real
unauthenticated sign-in page was visually verified. Signed-in production UI
was not verified. No production DDL or production record query was performed.

## Renewed owner review and additional readiness scan (2026-10-02)

The owner explicitly approved the four redundant index removals and renewed the
production count-only Goals preflight permission. After reconfirming the table
and required columns in the read-only production replica, the exact documented
all-dates predicate returned **0 total, 0 active, 0 archived, and 0 zero-amount
affected records**. No identities, record values, or financial totals were
retrieved, and no records were changed.

The newly merged opt-in Goals storage check was reviewed and executed using
fresh production metadata: the table and every required column are present and
visible in the replica. This is schema-only evidence, not signed-in runtime or
live-primary verification.

The additional dependency, static-code, and privacy scanners completed and
reported no findings. These scans do not prove the absence of vulnerabilities
or replace the required ownership, migration, browser, and restore tests.

A fresh Publish comparison contains the same twelve approved statements and no
warnings, structural-data-loss flag, or table/column removals. Its ordering
differs from the previous capture, so the second-release fixture was refreshed
to the actual current sequence for exact-order replay. The comparison still
flags possible backwards incompatibility, as expected for the reviewed index
removals and new integrity checks; this is not an overwrite-data release.

An orphaned development server left after workflow reconciliation was stopped.
The managed service restarted successfully with clean startup logs and the
unauthenticated sign-in screen was visually verified. Actual signed-in
production UI remains unverified. No production DDL, deployment configuration
change, publication, or record correction was performed.

The complete post-merge readiness gate passed: **974 passed, 0 failed,
2 skipped**, including the fresh exact-order Publish replay and the new Goals
metadata-check regressions. The two existing optional recovery/conversion-lock
skips remain; this result is not off-host backup or production sign-in proof.

A fresh schema-only replica check reconfirmed all four exact validated parent
unique constraints. The seven restoration FKs and manual-progress Goal check
are still absent. The release is ready for the **owner's second Publish**, not
yet a completed production repair. Review the twelve approved changes without
overwrite-data; if any additional destructive changes appear, stop. After the
owner reports completion, verify all seven exact validated FK definitions and
the Goal check through read-only production metadata before declaring the
repair complete and starting the approved Serenity Next waves.