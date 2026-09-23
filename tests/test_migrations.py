import os
import sqlite3
import subprocess
import sys


def run_alembic(database_path, *args):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{database_path}"}
    result = subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr


def test_alembic_head_builds_expected_sqlite_schema(tmp_path):
    database_path = tmp_path / "migration-test.db"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database_path}",
    }
    run_alembic(database_path, "upgrade", "head")

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
        assert "quantity_units" in investment_columns
        assert "active" in account_columns
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
    run_alembic(database_path, "upgrade", "head")
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