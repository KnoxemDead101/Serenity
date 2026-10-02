"""Goal Core migration tests use only disposable SQLite databases."""

import os
import sqlite3
import subprocess
import sys


def _alembic(database_path, *args):
    from conftest import TEST_CLERK_ISSUER

    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database_path}",
        "SERENITY_LEGACY_CLERK_ISSUER": TEST_CLERK_ISSUER,
        "SERENITY_CONFIRM_WORKSPACE_DOWNGRADE": "1",
        "SERENITY_LEGACY_OWNER_ID": "owner-a",
    }
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        env=env, capture_output=True, text=True, timeout=90,
    )


def _tables(connection):
    return {
        row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }


def _seed_pre_goal_financial_rows(connection):
    """Seed representative legacy rows without running the application."""
    now = "2026-09-30 12:00:00"
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at, owner_id) "
        "VALUES (91001, 'Pre-goal cash', 'Checking', 'Personal', 123456, 1, ?, ?, ?)",
        (now, now, "owner-a"),
    )
    connection.execute(
        "INSERT INTO debts (id, name, debt_type, balance_cents, "
        "interest_rate_milli, minimum_payment_cents, created_at, updated_at, "
        "owner_id, active) "
        "VALUES (91001, 'Pre-goal liability', 'Credit Card', 654321, "
        "6875, 2500, ?, ?, ?, 1)",
        (now, now, "owner-a"),
    )


def test_goal_migration_is_additive_and_preserves_existing_financial_rows(tmp_path):
    path = tmp_path / "goal-additive.db"
    previous = _alembic(path, "upgrade", "0017_portfolio_holdings")
    assert previous.returncode == 0, previous.stderr
    with sqlite3.connect(path) as connection:
        _seed_pre_goal_financial_rows(connection)
        connection.commit()
        before = _tables(connection)

    upgraded = _alembic(path, "upgrade", "0018_goal_core")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        assert _tables(connection) == before | {"goals"}
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0018_goal_core",)
        assert connection.execute(
            "SELECT name, opening_balance_cents, owner_id FROM accounts "
            "WHERE id = 91001"
        ).fetchone() == ("Pre-goal cash", 123456, "owner-a")
        assert connection.execute(
            "SELECT name, balance_cents, interest_rate_milli, owner_id "
            "FROM debts WHERE id = 91001"
        ).fetchone() == (
            "Pre-goal liability", 654321, 6875, "owner-a",
        )
        columns = {
            row[1]: row for row in connection.execute("PRAGMA table_info(goals)")
        }
        assert {
            "id", "owner_id", "name", "description", "goal_type", "category",
            "status", "priority", "target_date", "target_amount_cents",
            "current_progress_amount_cents", "progress_source", "notes",
            "active", "completed_at", "created_at", "updated_at",
        } <= set(columns)
        assert columns["owner_id"][3] == 1
        assert columns["target_amount_cents"][3] == 0
        assert columns["current_progress_amount_cents"][3] == 0
        assert "ix_goals_owner_id" in {
            row[1] for row in connection.execute("PRAGMA index_list(goals)")
        }
        assert not connection.execute("PRAGMA foreign_key_list(goals)").fetchall()
        assert any(
            unique and {
                column[2]
                for column in connection.execute(
                    "PRAGMA index_info(" + index_name + ")"
                )
            } == {"owner_id", "id"}
            for index_name, unique in (
                (row[1], row[2])
                for row in connection.execute("PRAGMA index_list(goals)")
            )
        )


def test_goal_migration_refuses_populated_downgrade_then_allows_empty_downgrade(
    tmp_path,
):
    path = tmp_path / "goal-downgrade.db"
    migrated = _alembic(path, "upgrade", "head")
    assert migrated.returncode == 0, migrated.stderr
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO goals (owner_id, name, goal_type, category, status, "
            "priority, progress_source, active, created_at, updated_at) "
            "VALUES ('owner-a', 'Keep this goal', 'SAVINGS', 'FINANCIAL', "
            "'NOT_STARTED', 'NORMAL', 'MANUAL', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.commit()

    refused = _alembic(path, "downgrade", "0017_portfolio_holdings")
    assert refused.returncode != 0
    assert "Cannot downgrade Goal Core" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert {row[0] for row in connection.execute(
            "SELECT version_num FROM alembic_version"
        )} == {"0018_goal_core", "0017_conversion_guards"}
        assert connection.execute("SELECT name FROM goals").fetchone() == (
            "Keep this goal",
        )

        connection.execute("DELETE FROM goals")
        connection.commit()

    allowed = _alembic(path, "downgrade", "0017_portfolio_holdings")
    assert allowed.returncode == 0, allowed.stderr
    with sqlite3.connect(path) as connection:
        assert {row[0] for row in connection.execute(
            "SELECT version_num FROM alembic_version"
        )} == {"0017_portfolio_holdings", "0017_conversion_guards"}
        assert "goals" not in _tables(connection)
        assert "reconciliation_approvals" in _tables(connection)
        assert {"accounts", "debts", "investments", "portfolios"} <= _tables(
            connection
        )


def test_empty_database_can_upgrade_and_downgrade_goal_core(tmp_path):
    path = tmp_path / "empty-goal-database.db"
    upgraded = _alembic(path, "upgrade", "0018_goal_core")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        assert "goals" in _tables(connection)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0018_goal_core",)

    downgraded = _alembic(path, "downgrade", "0017_portfolio_holdings")
    assert downgraded.returncode == 0, downgraded.stderr
    with sqlite3.connect(path) as connection:
        assert "goals" not in _tables(connection)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0017_portfolio_holdings",)