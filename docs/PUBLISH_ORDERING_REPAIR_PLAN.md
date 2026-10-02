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