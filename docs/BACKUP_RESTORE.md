# Database backup and restore rehearsal

JSON/CSV exports are useful reports, **not recoverable database backups**.
This rehearsal uses synthetic records only. It does not read or replace the
running app's database, contact Clerk, or change authentication configuration.
It is separate from the published sign-in verification.

## Repeat the rehearsal

From the repository root, with the project's Python dependencies available:

```sh
python scripts/rehearse_database_restore.py --backend sqlite
python scripts/rehearse_database_restore.py --backend postgresql
pytest -q tests/test_backup_restore.py
# Require the PostgreSQL integration check as well (missing tools fail the test):
SERENITY_REQUIRE_POSTGRES_RESTORE=1 pytest -q tests/test_backup_restore.py
```

PostgreSQL additionally needs `initdb`, `pg_ctl`, `createdb`, `pg_dump`, and
`pg_restore` from the same PostgreSQL installation on PATH. Run as a non-root
user. The PostgreSQL rehearsal starts its own temporary local cluster, not
the managed development/production server. Its socket is in a private
temporary directory and TCP listening is disabled. No credentials are needed.
Missing prerequisites or any failed comparison must produce a nonzero exit;
do not treat an unavailable PostgreSQL run as a successful rehearsal.

The script accepts a backend choice, **not a database URL or restore target**.
It ignores the application's `DATABASE_URL` and PostgreSQL connection settings.
Both the source and destination are freshly created and disposable. It applies
Alembic migrations to the source, seeds multiple synthetic owners, makes a
native backup, and restores into an empty destination:

- SQLite: SQLite's online backup API, then restore with the same API.
- PostgreSQL: `pg_dump --format=custom`, then
  `pg_restore --exit-on-error --no-owner --no-acl`.

Success requires matching complete table contents, including row identifiers,
integer financial values, timestamps, owner IDs, links, transaction correction
history, income profiles, and `alembic_version`. Service-level checks confirm
the calculated balances and planned income still agree and one owner cannot
read another's records. The restored database must already be at the expected
Alembic revision: upgrading or stamping it before checking would hide loss.
Temporary files, the backup, and the temporary cluster are removed on normal
completion and handled failures. A forcibly killed process or host crash may
leave temporary files; remove only the identified rehearsal directory after
ensuring its PostgreSQL process has stopped.

The synthetic JSON success report is safe to retain as evidence. Do not commit
database files, dumps, credentials, service configuration, or real-data reports.
Temporary files have private permissions. Real backups additionally require
encryption, restricted access, and storage independent of the application host.
Git ignore rules reduce accidental commits; they are not encryption or access
control, and a forced Git add bypasses them.

## Intended PostgreSQL deployment: operator recovery procedure

The local rehearsal establishes a database-native round trip on a disposable
server. Before real data or a host move, repeat recovery on the **chosen host
and PostgreSQL version**, using an isolated destination and the intended backup
storage. The rehearsal is not a production backup schedule or a hosting test.

1. Define the acceptable data-loss window (RPO), recovery time (RTO), retention,
   backup owner, encryption-key recovery, and alert recipient. Configure
   automated encrypted off-host backups. Take a backup before every upgrade.
   For tighter RPO, use the provider's tested physical backups/WAL point-in-time
   recovery in addition to logical dumps.
2. Use a least-privilege backup connection configured by the host's secret
   manager. Prefer a protected PostgreSQL service file and password file
   (mode 0600); never put passwords in command arguments, shell history, Git,
   or reports. Do not echo connection strings. On remote connections verify
   TLS and the server identity.
3. `pg_dump` takes a consistent snapshot while the database is running.
   It does not include commits after the snapshot. For a cutover, stop app
   writers and background writers, take a final backup, and keep them stopped
   until the new database is verified. Use a dump client compatible with the
   server; do not restore into an older major version.
4. A DBA must provision a **new, empty, explicitly disposable** restore
   database, owned by the intended application role. Check host, database name,
   and emptiness independently. Never point the restore at the current
   development or production database. Do not use `--clean`, `--create`,
   `dropdb`, or an in-place restore against a populated database.
5. Example commands below use service aliases the operator must deliberately
   configure; these aliases are NOT provided by Serenity. `serenity_backup`
   identifies the approved source; `serenity_restore_isolated` identifies only
   the newly provisioned destination. Use a protected directory outside the
   repository on encrypted storage:

   ```sh
   umask 077
   # Set BACKUP_DIR to a new private directory on encrypted storage first.
   : "${BACKUP_DIR:?Choose a new private backup directory outside the repository}"
   test ! -e "$BACKUP_DIR/serenity.dump" || exit 1
   pg_dump --dbname='service=serenity_backup' --format=custom \
     --file="$BACKUP_DIR/serenity.dump" &&
   sha256sum "$BACKUP_DIR/serenity.dump" > "$BACKUP_DIR/serenity.dump.sha256"
   # Stop here if backup creation fails. Verify transferred files before use.
   (cd "$BACKUP_DIR" && sha256sum --check serenity.dump.sha256)
   # Only after independently confirming the restore target is new and empty:
   pg_restore --dbname='service=serenity_restore_isolated' \
     --exit-on-error --single-transaction --no-owner --no-acl \
     "$BACKUP_DIR/serenity.dump"
   ```

   Stop on any failed command. A checksum detects transfer corruption, not
   malicious changes; protect the checksum with the backup. Encrypt before
   transferring off host and test that keys are recoverable.
6. Against the isolated destination, check the stored Alembic revision
   against the source's recorded revision **before any migrations**. Using
   the corresponding application version, compare every table's row counts
   and full contents or canonical digests, including corrections and owner
   IDs. Independently verify selected owners' opening balances, corrected
   income/expenses, computed balances, and planned income. Test cross-owner
   denial. Run a rollback-only insert check to confirm generated IDs/sequences
   allow future writes. Avoid logging real financial data or owner identifiers.
7. Application `owner_id` values must remain unchanged. `--no-owner --no-acl`
   omits PostgreSQL role ownership/grants, **not Serenity record ownership**.
   Reapply least-privilege grants separately. A database dump does not back up
   cluster roles, provider settings, secrets, Clerk users/sessions, encryption
   keys, uploads stored elsewhere, or application source. Preserve those through
   separately controlled procedures. Moving Clerk tenants needs an explicitly
   audited identity mapping; restoring the database cannot perform that mapping.
8. Record backup timestamp, PostgreSQL/client versions, app version, revision,
   checksum, elapsed recovery time, and pass/fail results in private operational
   evidence. Have the operator approve cutover; keep the previous database and
   rollback backup intact. Change the application's secret-managed connection
   only after validation, restart processes, and complete authenticated checks.
   Do not delete rollback copies until the retention policy permits it.

## SQLite limitations

- Use SQLite only with a single application instance on a persistent volume.
  A relative development path or ephemeral deployment filesystem is not durable
  storage.
- Do not copy just a live `.db` file: committed changes can still be in `-wal`,
  and copying `.db`, `-wal`, and `-shm` independently is not a consistent snapshot.
  Use the SQLite backup API as rehearsed, or shut down all writers cleanly
  before a controlled offline file copy.
- Restore into a **different** file, run `PRAGMA integrity_check` and
  `PRAGMA foreign_key_check`, verify the data/revision, then plan an offline
  cutover. Never overwrite a database that any process has open.
- SQLite backup files are SQLite databases, not PostgreSQL dumps. This rehearsal
  tests each backend independently; it does **not** migrate SQLite data into
  PostgreSQL. That move needs a separately verified data conversion with
  ownership, integer amounts, timestamps, links, and sequences preserved.
- SQLite's timestamp representation and concurrency differ from PostgreSQL.
  Passing the SQLite rehearsal alone does not prove the PostgreSQL path.

## Evidence

On September 23, 2026, both CLI rehearsals passed locally, using SQLite and
PostgreSQL 17.5. Both restored revision `0010_income_profiles`, four accounts,
six transactions, four correction records, two income profiles, two businesses,
and two dependents across two synthetic owners. Each owner's calculated balance
was `163.00`; active/inactive income profiles and income projections matched.
All-table comparison includes the currently empty bills, debts, and investments
tables; this fixture does not establish nonempty recovery examples for those
three tables. SQLite integrity/foreign-key checks and PostgreSQL's generated-ID
probe passed.

After environment-isolation hardening,
`SERENITY_REQUIRE_POSTGRES_RESTORE=1 pytest -q tests/test_backup_restore.py`
passed **8 tests**, including both native round trips, mismatch detection,
ambient-database protection, failure cleanup/environment restoration, rejected
target arguments, and foreign-key corruption detection. Two existing
test-library deprecation warnings remain. The SQLite CLI also emitted SQLAlchemy
warnings about expression-index reflection; row comparison still passed.

This is synthetic local evidence, not a production backup, live-data recovery,
external-host deployment, or published sign-in verification.