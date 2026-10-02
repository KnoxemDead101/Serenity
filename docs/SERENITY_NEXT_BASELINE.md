# Serenity Next — Wave 0 engineering baseline

Run from the repository root:

```sh
bash scripts/serenity_next_check.sh
```

The project's named `test` validation runs this stricter command. The ordinary
Run group starts only the managed Serenity web service, not the test suite.

This is a one-off engineering check, not the normal app Run command or a
deployment/startup hook. It adds no dependencies, changes no application schema,
and never publishes the app.

## Required proof

The baseline wraps the existing fail-closed publishing gate, requiring its
entire test suite, disposable PostgreSQL migrations, ownership checks, and
Chromium/Playwright browser tests. It also requires the existing PostgreSQL
database-native backup/restore rehearsal rather than silently skipping it.
SQLite recovery remains covered by the existing suite.

The cross-session financial-lock test now uses the same fixture-created private
PostgreSQL cluster as the rest of the integration tests. It no longer accepts
an inherited `TEST_POSTGRESQL_URL`. The fixture supplies an isolated temporary
Unix socket; the test checks that boundary before obtaining advisory locks.

The underlying gate clears inherited PostgreSQL connection settings and selects
disposable storage. Failed checks propagate their nonzero exit status; a failed
run cannot print the baseline-passed message.

## What this does not prove

- The current production schema or signed-in published screens.
- Completeness or correctness of real financial records.
- Automated off-host backups, host-loss recovery, or encryption-key recovery.
- Scheduled outage detection or physical status-history cleanup.
- Live market-data provenance, trading readiness, or broker execution.

System Console must keep these evidence classes distinct. A local synthetic
round trip is not permission to replace a running database or change financial
write authority. Production changes remain owner-operated managed Publish.

## Initial verified result — 2026-10-02

The managed `test` run passed **1,171 tests, 0 failed, 0 skipped** in 851 seconds.
PostgreSQL restore and cross-session financial-lock checks were required, not
skipped. Two pre-existing test-client deprecation warnings remain. An earlier
shell run interrupted by a workspace restart was discarded as incomplete.

The actual Run group was independently checked to invoke only the managed web
service; the named test command invokes this baseline. The app is running and
the unauthenticated sign-in page was visually checked. Signed-in production UI
and off-host recovery remain outside this proof.

## Carrying evidence into the next wave

Record the tested source checkpoint, date, actual pass/fail/skip counts, and any
remaining limitations in the chat handoff after the gate completes. Rerun after
material code/schema changes; do not reuse an older passing result as proof of a
newer implementation. Keep generated diagnostic logs outside public source.