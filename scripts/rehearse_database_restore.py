"""Rehearse native backup/restore exclusively in newly created disposable databases.

Usage: python scripts/rehearse_database_restore.py --backend sqlite
       python scripts/rehearse_database_restore.py --backend postgresql
No database location is accepted from the caller or inherited from DATABASE_URL.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OWNERS = ("rehearsal-owner-a", "rehearsal-owner-b")


class RehearsalError(RuntimeError):
    """A verification step failed (details must not include connection strings)."""


def command(args, *, env=None, cwd=ROOT):
    """Do not forward command output: PostgreSQL/driver errors can contain credentials."""
    try:
        subprocess.run(
            args, cwd=cwd, env=env, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, check=True, timeout=120,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RehearsalError(f"Disposable database command failed: {Path(args[0]).name}") from None


def isolated_env(url):
    env = {key: value for key, value in os.environ.items()
           if key != "DATABASE_URL" and not key.startswith("PG")
           and key != "SERENITY_LEGACY_OWNER_ID"}
    env["DATABASE_URL"] = url
    return env


def migrate_source(url):
    command([sys.executable, "-m", "alembic", "upgrade", "head"], env=isolated_env(url))


def head_revision():
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    heads = ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_heads()
    if len(heads) != 1:
        raise RehearsalError("Expected exactly one Alembic head")
    return heads[0]


def canonical(value):
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, bytes):
        return value.hex()
    if isinstance(value, dict):
        return {key: canonical(item) for key, item in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [canonical(item) for item in value]
    return value


def table_snapshot(engine):
    """All user tables, all columns, including revision, owner, IDs and timestamps."""
    from sqlalchemy import MetaData, Table, inspect, select

    result = {}
    with engine.connect() as conn:
        for name in sorted(inspect(conn).get_table_names()):
            table = Table(name, MetaData(), autoload_with=conn)
            rows = [
                {column: canonical(value) for column, value in row._mapping.items()}
                for row in conn.execute(select(table))
            ]
            result[name] = sorted(rows, key=lambda row: json.dumps(row, sort_keys=True))
    return result


def assert_same(source, restored):
    if source.keys() != restored.keys():
        raise RehearsalError("Restored table set differs from source")
    for name in source:
        if source[name] != restored[name]:
            raise RehearsalError(f"Restored rows differ in table {name}")


def check_revision(snapshot, head):
    rows = snapshot.get("alembic_version")
    if rows != [{"version_num": head}]:
        raise RehearsalError("Restored Alembic revision is not the current head")


def seed(engine):
    """Import the app only after source migration and disposable URL binding."""
    from sqlalchemy.orm import Session
    from schemas.account import AccountCreate
    from schemas.business import BusinessCreate
    from schemas.dependent import DependentCreate
    from schemas.income_profile import IncomeProfileCreate
    from schemas.transaction import TransactionCreate, TransactionUpdate
    from services import (
        account_service as accounts, business_service as businesses,
        dependent_service as dependents, income_profile_service as incomes,
        transaction_service as transactions,
    )

    with Session(engine) as db:
        for index, owner in enumerate(OWNERS):
            other = OWNERS[1 - index]
            account = accounts.create_account(
                db, AccountCreate(name=f"Checking {index}", account_type="Checking",
                                  classification="Personal", opening_balance="100.00"), owner,
            )
            extra = accounts.create_account(
                db, AccountCreate(name=f"Savings {index}", account_type="Savings",
                                  classification="Personal", opening_balance="25.00"), owner,
            )
            business = businesses.create_business(db, BusinessCreate(name=f"Shop {index}"), owner)
            dependent = dependents.create_dependent(
                db, DependentCreate(display_name=f"Child {index}"), owner,
            )
            income = transactions.create_transaction(
                db, account, TransactionCreate(date="2026-09-22", transaction_type="Income",
                                                amount="50.00", description="Paycheck"),
            )
            expense = transactions.create_transaction(
                db, account, TransactionCreate(
                    date="2026-09-23", transaction_type="Expense", amount="10.00",
                    description="Supplies", business_id=business.id, dependent_id=dependent.id,
                ),
            )
            transactions.update_transaction(
                db, expense, TransactionUpdate(
                    date="2026-09-23", transaction_type="Expense", amount="12.00",
                    description="Corrected supplies", business_id=business.id,
                    dependent_id=dependent.id,
                ),
            )
            deleted = transactions.create_transaction(
                db, extra, TransactionCreate(date="2026-09-23", transaction_type="Expense",
                                              amount="2.00", description="Duplicate"),
            )
            transactions.delete_transaction(db, deleted)
            profile = incomes.create_income_profile(
                db, IncomeProfileCreate(name=f"Salary {index}", income_type="Salary",
                                        pay_frequency="Monthly", annual_salary="60000.00",
                                        expected_net_per_period="4000.00"), owner,
            )
            if index:
                incomes.set_income_profile_active(db, profile, False)
            # Explicit negative owner reads, both directions, for every seeded family.
            if (accounts.get_account(db, account.id, other) is not None
                    or transactions.get_transaction(db, account.id, income.id, other) is not None
                    or transactions.list_transactions(db, account.id, other)
                    or transactions.list_corrections(db, account.id, other)
                    or businesses.get_business(db, business.id, other) is not None
                    or dependents.get_dependent(db, dependent.id, other) is not None
                    or incomes.get_income_profile(db, profile.id, other) is not None):
                raise RehearsalError("Cross-owner read succeeded")
    return True


def service_reads(engine):
    from sqlalchemy.orm import Session
    from services import (
        account_service as accounts, dashboard_service as dashboard,
        income_profile_service as incomes, transaction_service as transactions,
    )

    result = {}
    with Session(engine) as db:
        for index, owner in enumerate(OWNERS):
            other = OWNERS[1 - index]
            owned = accounts.list_accounts(db, owner)
            profiles = incomes.list_income_profiles(db, owner)
            if len(owned) != 2 or len(profiles) != 1:
                raise RehearsalError("Owner-scoped records missing")
            for account in owned:
                if (accounts.get_account(db, account.id, other) is not None
                        or transactions.list_transactions(db, account.id, other)
                        or transactions.list_corrections(db, account.id, other)):
                    raise RehearsalError("Cross-owner account or history read succeeded")
            if incomes.get_income_profile(db, profiles[0].id, other) is not None:
                raise RehearsalError("Cross-owner income read succeeded")
            result[owner] = canonical({
                "accounts": [accounts.to_account_read(item).model_dump(mode="json") for item in owned],
                "transactions": [
                    transactions.to_transaction_read(item).model_dump(mode="json")
                    for account in owned
                    for item in transactions.list_transactions(db, account.id, owner)
                ],
                "corrections": [
                    transactions.to_correction_read(item).model_dump(mode="json")
                    for account in owned
                    for item in transactions.list_corrections(db, account.id, owner)
                ],
                "income_profiles": [
                    incomes.to_income_profile_read(item).model_dump(mode="json") for item in profiles
                ],
                "income_summary": incomes.get_income_summary(db, owner).model_dump(mode="json"),
                "account_totals": accounts.get_account_totals(db, owner).model_dump(mode="json"),
                "dashboard": dashboard.get_dashboard_summary(db, owner).model_dump(mode="json"),
            })
    return result


def sqlite_backup_restore(source, backup, restored):
    """Backup API provides a consistent native copy; restore into another new file."""
    with sqlite3.connect(source) as src, sqlite3.connect(backup) as native:
        src.backup(native)
    with sqlite3.connect(backup) as native, sqlite3.connect(restored) as dst:
        native.backup(dst)
    for path in (source, backup, restored):
        sqlite_integrity(path)


def sqlite_integrity(path):
    with sqlite3.connect(path) as connection:
        if connection.execute("PRAGMA integrity_check").fetchall() != [("ok",)]:
            raise RehearsalError("SQLite integrity check failed")
        if connection.execute("PRAGMA foreign_key_check").fetchall():
            raise RehearsalError("SQLite foreign key check failed")


def check_restored_sequence(engine):
    """Rollback-only insert proves pg_restore restored the next generated ID."""
    from datetime import datetime, timezone
    from sqlalchemy import text

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            highest = connection.execute(text("SELECT max(id) FROM accounts")).scalar_one()
            generated = connection.execute(text(
                "INSERT INTO accounts (owner_id, name, account_type, classification, "
                "opening_balance_cents, active, created_at, updated_at) "
                "VALUES (:owner, 'Sequence probe', 'Checking', 'Personal', "
                "0, true, :now, :now) RETURNING id"
            ), {"owner": OWNERS[0], "now": datetime.now(timezone.utc)}).scalar_one()
            if generated <= highest:
                raise RehearsalError("Restored generated account ID overlaps existing rows")
        finally:
            transaction.rollback()


def postgres_binary(name):
    path = shutil.which(name)
    if path:
        return path
    pg_config = shutil.which("pg_config")
    if pg_config:
        try:
            bindir = subprocess.run(
                [pg_config, "--bindir"], check=True, capture_output=True,
                text=True, timeout=10,
                env={key: value for key, value in os.environ.items()
                     if key != "DATABASE_URL" and not key.startswith("PG")},
            ).stdout.strip()
            candidate = Path(bindir) / name
            if candidate.is_file() and os.access(candidate, os.X_OK):
                return str(candidate)
        except (OSError, subprocess.SubprocessError):
            pass
    raise RehearsalError(f"Local PostgreSQL binary unavailable: {name}")


def postgres_cluster(directory):
    """Private local cluster, no TCP listener and no externally supplied endpoint."""
    from contextlib import contextmanager
    from sqlalchemy.engine import URL

    @contextmanager
    def cluster():
        tools = {name: postgres_binary(name) for name in
                 ("initdb", "pg_ctl", "createdb", "pg_dump", "pg_restore")}
        data = directory / "cluster"
        socket = directory / "socket"
        socket.mkdir(mode=0o700)
        env = isolated_env("")
        env.pop("DATABASE_URL")
        command([tools["initdb"], "-D", str(data), "-A", "trust", "-U", "rehearsal"], env=env)
        start_attempted = False
        started = False
        try:
            start_attempted = True
            command([tools["pg_ctl"], "-D", str(data), "-l", str(directory / "server.log"),
                     "-o", f"-c listen_addresses='' -k {socket} -p 5432",
                     "-w", "start"], env=env)
            started = True
            for name in ("source", "restored"):
                command([tools["createdb"], "-h", str(socket), "-p", "5432",
                         "-U", "rehearsal", name], env=env)

            def url(name):
                return URL.create("postgresql+psycopg", username="rehearsal", database=name,
                                  query={"host": str(socket), "port": "5432"}).render_as_string(
                                      hide_password=False)

            yield url("source"), url("restored"), tools, socket, env
        finally:
            if start_attempted:
                try:
                    command([tools["pg_ctl"], "-D", str(data), "-m", "immediate",
                             "-w", "stop"], env=env)
                except RehearsalError:
                    # A failed start might have left no server to stop.
                    if started:
                        raise RehearsalError("Could not stop disposable PostgreSQL cluster") from None

    return cluster()


def postgres_backup_restore(tools, socket, directory, env):
    dump = directory / "native.dump"
    common = ["-h", str(socket), "-p", "5432", "-U", "rehearsal"]
    command([tools["pg_dump"], *common, "-Fc", "-f", str(dump), "source"], env=env)
    command([tools["pg_restore"], *common, "--exit-on-error", "--no-owner", "--no-acl",
             "-d", "restored", str(dump)], env=env)


def verify(source_url, restored_url, backend, restore):
    from sqlalchemy import create_engine

    # This assignment precedes any app/model/service import; never bind the ambient URL.
    os.environ["DATABASE_URL"] = source_url
    migrate_source(source_url)
    source = create_engine(source_url)
    restored = None
    try:
        seed(source)
        expected = table_snapshot(source)
        head = head_revision()
        check_revision(expected, head)
        reads = service_reads(source)
        source.dispose()
        restore()
        restored = create_engine(restored_url)
        actual = table_snapshot(restored)
        check_revision(actual, head)  # No migration or stamp is ever run on restored.
        assert_same(expected, actual)
        if service_reads(restored) != reads:
            raise RehearsalError("Restored owner-scoped service reads differ")
        if backend == "postgresql":
            check_restored_sequence(restored)
        return {
            "backend": backend,
            "revision": head,
            "table_rows": {table: len(rows) for table, rows in expected.items()},
            "owner_balances": {owner: data["dashboard"]["total_balance"]
                               for owner, data in reads.items()},
            "checks": ["alembic_head", "all_table_rows", "owner_isolation",
                       "balances", "income_projections", "correction_history",
                       "generated_id_sequence" if backend == "postgresql"
                       else "sqlite_integrity_and_foreign_keys"],
        }
    finally:
        source.dispose()
        if restored is not None:
            restored.dispose()


def rehearse(backend):
    if backend not in ("sqlite", "postgresql"):
        raise RehearsalError("Backend must be sqlite or postgresql")
    old_umask = os.umask(0o077)
    ambient_url = os.environ.get("DATABASE_URL")
    ambient_pg = {key: value for key, value in os.environ.items() if key.startswith("PG")}
    for key in ambient_pg:
        os.environ.pop(key, None)
    try:
        with tempfile.TemporaryDirectory(prefix="serenity-restore-") as temp:
            directory = Path(temp)
            if backend == "sqlite":
                from sqlalchemy.engine import URL

                source, backup, restored = (directory / name for name in
                                            ("source.db", "backup.db", "restored.db"))
                source_url = URL.create("sqlite", database=str(source)).render_as_string()
                restored_url = URL.create("sqlite", database=str(restored)).render_as_string()
                return verify(source_url, restored_url, backend,
                              lambda: sqlite_backup_restore(source, backup, restored))
            with postgres_cluster(directory) as (source_url, restored_url, tools, socket, env):
                return verify(source_url, restored_url, backend,
                              lambda: postgres_backup_restore(tools, socket, directory, env))
    finally:
        for key in list(os.environ):
            if key.startswith("PG"):
                os.environ.pop(key, None)
        os.environ.update(ambient_pg)
        if ambient_url is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = ambient_url
        os.umask(old_umask)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--backend", choices=("sqlite", "postgresql"), required=True)
    args = parser.parse_args(argv)
    try:
        result = rehearse(args.backend)
    except Exception:
        # Never print driver/subprocess exception strings: they can contain credentials/URLs.
        print(
            "Restore rehearsal failed; check for leftover serenity-restore "
            "temporary directories or processes.", file=sys.stderr,
        )
        return 1
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    sys.exit(main())