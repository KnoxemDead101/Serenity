"""Migration tests build throwaway SQLite databases through Alembic."""

import os
import sqlite3
import subprocess
import sys


def run_alembic(database_path, *args, extra_env=None):
    """Run an Alembic command against a fresh SQLite file."""
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database_path}"}
    env.update(extra_env or {})
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def index_names(connection, table):
    return {row[1] for row in connection.execute(f"PRAGMA index_list({table})")}


def test_alembic_head_builds_expected_sqlite_schema(tmp_path):
    database_path = tmp_path / "migration-test.db"
    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )

    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "accounts", "bills", "debts", "investments", "transactions",
            "transaction_corrections", "alembic_version",
        } <= tables

        debt_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(debts)")
        }
        investment_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(investments)")
        }
        account_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(accounts)")
        }
        assert "interest_rate_milli" in debt_columns
        assert "debt_type" in debt_columns
        assert "active" in debt_columns
        assert "quantity_units" in investment_columns
        assert "active" in investment_columns
        assert "active" in account_columns
        bill_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(bills)")
        }
        assert "active" in bill_columns
        transaction_columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(transactions)")
        }
        assert {
            "account_id", "date", "transaction_type", "classification",
            "amount_cents", "description", "merchant", "location", "category",
            "subcategory", "created_at", "updated_at", "deleted_at",
        } <= set(transaction_columns)
        assert transaction_columns["classification"][3] == 1
        assert transaction_columns["updated_at"][3] == 1
        assert connection.execute("PRAGMA foreign_key_list(transactions)").fetchone()[2] == "accounts"
        indexes = {row[1] for row in connection.execute("PRAGMA index_list(transactions)")}
        assert "ix_transactions_account_date" in indexes
        correction_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(transaction_corrections)")
        }
        assert {"account_id", "transaction_id", "action", "changed_at", "before", "after"} <= correction_columns
    finally:
        connection.close()


def test_0004_converts_existing_transactions(tmp_path):
    """Existing legacy transaction values are converted and backfilled."""
    database_path = tmp_path / "data-migration-test.db"
    run_alembic(database_path, "upgrade", "0003_transaction_corrections")
    connection = sqlite3.connect(database_path)
    now = "2026-09-22 12:00:00"
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at) "
        "VALUES (1, 'Checking', 'Business Checking', 'Business', 0, 1, ?, ?)",
        (now, now),
    )
    connection.executemany(
        "INSERT INTO transactions (id, account_id, date, transaction_type, "
        "amount_cents, description, created_at) VALUES (?, 1, '2026-09-20', ?, ?, ?, ?)",
        [(1, "Deposit", 5000, "Client payment", now),
         (2, "Withdrawal", 1250, "Postage", now)],
    )
    connection.commit()
    connection.close()
    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )
    connection = sqlite3.connect(database_path)
    try:
        rows = connection.execute(
            "SELECT id, transaction_type, classification, amount_cents, updated_at "
            "FROM transactions ORDER BY id"
        ).fetchall()
    finally:
        connection.close()
    assert [(row[0], row[1], row[2], row[3]) for row in rows] == [
        (1, "Income", "Business", 5000), (2, "Expense", "Business", 1250),
    ]
    assert all(row[4] is not None for row in rows)
    run_alembic(database_path, "downgrade", "0003_transaction_corrections")
    connection = sqlite3.connect(database_path)
    try:
        types = [row[0] for row in connection.execute(
            "SELECT transaction_type FROM transactions ORDER BY id")]
    finally:
        connection.close()
    assert types == ["Deposit", "Withdrawal"]


def test_0005_upgrades_and_downgrades_cleanly(tmp_path):
    """The timezone migration is a no-op on SQLite but preserves timestamps."""
    database_path = tmp_path / "timestamps-test.db"
    run_alembic(database_path, "upgrade", "0004_align_transactions_v02")
    connection = sqlite3.connect(database_path)
    now = "2026-09-23 12:00:00"
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at) "
        "VALUES (1, 'Checking', 'Checking', 'Personal', 0, 1, ?, ?)",
        (now, now),
    )
    connection.commit()
    connection.close()

    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )
    run_alembic(database_path, "downgrade", "0004_align_transactions_v02")
    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )

    connection = sqlite3.connect(database_path)
    try:
        created = connection.execute(
            "SELECT created_at FROM accounts WHERE id = 1"
        ).fetchone()[0]
    finally:
        connection.close()
    assert created == now


def test_0006_preserves_existing_finance_rows_as_active(tmp_path):
    """Existing rows receive active=true when lifecycle flags are added."""
    database_path = tmp_path / "active-flags-test.db"
    run_alembic(database_path, "upgrade", "0005_timezone_aware_timestamps")
    connection = sqlite3.connect(database_path)
    now = "2026-09-23 12:00:00"
    connection.execute(
        "INSERT INTO bills (id, name, amount_cents, due_date, frequency, "
        "created_at, updated_at) VALUES (1, 'Rent', 120000, '2026-10-01', "
        "'Monthly', ?, ?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO debts (id, name, debt_type, balance_cents, "
        "interest_rate_milli, minimum_payment_cents, created_at, updated_at) "
        "VALUES (1, 'Card', 'Credit Card', 5000, 6875, 100, ?, ?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO investments (id, name, quantity_units, cost_basis_cents, "
        "current_value_cents, created_at, updated_at) "
        "VALUES (1, 'Fund', 100000000, 10000, 11000, ?, ?)",
        (now, now),
    )
    connection.commit()
    connection.close()

    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )
    connection = sqlite3.connect(database_path)
    try:
        for table in ("bills", "debts", "investments"):
            assert connection.execute(
                f"SELECT active FROM {table} WHERE id = 1"
            ).fetchone()[0] == 1
    finally:
        connection.close()


def test_0007_preserves_existing_transactions_and_adds_optional_links(tmp_path):
    """Business/dependent links are nullable so old transactions survive."""
    database_path = tmp_path / "business-links-test.db"
    run_alembic(database_path, "upgrade", "0006_active_flags")
    connection = sqlite3.connect(database_path)
    now = "2026-09-23 12:00:00"
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at) "
        "VALUES (1, 'Checking', 'Checking', 'Personal', 0, 1, ?, ?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO transactions (id, account_id, date, transaction_type, "
        "classification, amount_cents, description, created_at, updated_at) "
        "VALUES (1, 1, '2026-09-23', 'Expense', 'Personal', 500, "
        "'Existing', ?, ?)",
        (now, now),
    )
    connection.commit()
    connection.close()

    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {"businesses", "dependents"} <= tables
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(transactions)")
        }
        assert {"business_id", "dependent_id"} <= columns
        assert connection.execute(
            "SELECT description, business_id, dependent_id "
            "FROM transactions WHERE id = 1"
        ).fetchone() == ("Existing", None, None)
        foreign_tables = {
            row[2] for row in connection.execute(
                "PRAGMA foreign_key_list(transactions)"
            )
        }
        assert {"accounts", "businesses", "dependents"} <= foreign_tables
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(transactions)")
        }
        assert "ix_transactions_account_date" in indexes
    finally:
        connection.close()


def test_0008_requires_an_explicit_owner_for_existing_data(tmp_path):
    """Ownership migration refuses to guess who owns legacy financial data."""
    database_path = tmp_path / "ownership-required-test.db"
    run_alembic(database_path, "upgrade", "0007_business_and_dependents")
    connection = sqlite3.connect(database_path)
    now = "2026-09-23 12:00:00"
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at) "
        "VALUES (1, 'Checking', 'Checking', 'Personal', 0, 1, ?, ?)",
        (now, now),
    )
    connection.commit()
    connection.close()

    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "SERENITY_LEGACY_OWNER_ID is required" in result.stderr


def test_0008_backfills_all_existing_records_to_declared_owner(tmp_path):
    """The deliberate legacy assignment covers every protected record table."""
    database_path = tmp_path / "ownership-backfill-test.db"
    run_alembic(database_path, "upgrade", "0007_business_and_dependents")
    connection = sqlite3.connect(database_path)
    now = "2026-09-23 12:00:00"
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at) "
        "VALUES (1, 'Checking', 'Checking', 'Personal', 0, 1, ?, ?)",
        (now, now),
    )
    connection.execute(
        "INSERT INTO bills (id, name, amount_cents, due_date, frequency, "
        "created_at, updated_at) VALUES (1, 'Rent', 100, '2026-10-01', "
        "'Monthly', ?, ?)",
        (now, now),
    )
    connection.commit()
    connection.close()
    run_alembic(
        database_path, "upgrade", "head",
        extra_env={"SERENITY_LEGACY_OWNER_ID": "owner-a"},
    )

    connection = sqlite3.connect(database_path)
    try:
        for table in (
            "accounts", "bills", "debts", "investments", "businesses",
            "dependents", "transactions", "transaction_corrections",
        ):
            assert connection.execute(
                f"SELECT DISTINCT owner_id FROM {table}"
            ).fetchall() in ([], [("owner-a",)])
    finally:
        connection.close()


def test_0008_empty_database_needs_no_legacy_owner(tmp_path):
    path = tmp_path / "empty-ownership.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}"}
    env.pop("SERENITY_LEGACY_OWNER_ID", None)
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0008_record_ownership"],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_0009_adds_owner_lookup_indexes_and_downgrades(tmp_path):
    database_path = tmp_path / "owner-indexes-test.db"
    run_alembic(database_path, "upgrade", "0009_owner_id_indexes")
    connection = sqlite3.connect(database_path)
    try:
        expected = {
            "accounts": "ix_accounts_owner_id",
            "bills": "ix_bills_owner_id",
            "debts": "ix_debts_owner_id",
            "investments": "ix_investments_owner_id",
            "transactions": "ix_transactions_owner_id",
            "transaction_corrections": "ix_transaction_corrections_owner_id",
        }
        for table, index in expected.items():
            assert index in index_names(connection, table)
    finally:
        connection.close()
    run_alembic(database_path, "downgrade", "0008_record_ownership")
    run_alembic(database_path, "upgrade", "0009_owner_id_indexes")


def test_0010_creates_owner_scoped_income_profiles_and_downgrades(tmp_path):
    database_path = tmp_path / "income-profiles-test.db"
    run_alembic(database_path, "upgrade", "head")
    connection = sqlite3.connect(database_path)
    try:
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(income_profiles)")
        }
        assert {
            "owner_id", "name", "income_type", "classification", "pay_frequency",
            "hourly_rate_cents", "standard_hours_hundredths",
            "expected_hours_hundredths", "annual_salary_cents",
            "amount_per_period_cents", "expected_net_per_period_cents",
            "notes", "active", "created_at", "updated_at",
        } <= set(columns)
        assert columns["owner_id"][3] == 1
        assert columns["pay_frequency"][3] == 0
        assert "ix_income_profiles_owner_id" in index_names(connection, "income_profiles")
    finally:
        connection.close()
    run_alembic(database_path, "downgrade", "0009_owner_id_indexes")
    connection = sqlite3.connect(database_path)
    try:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "income_profiles" not in tables
    finally:
        connection.close()