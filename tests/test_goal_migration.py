"""Goal Core migration tests use only disposable SQLite databases."""

import os
import sqlite3
import subprocess
import sys

import pytest
from sqlalchemy import create_engine

from models.goal import Goal
from utils.choices import GOAL_PROGRESS_SOURCES


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


def _insert_progress(connection, source, amount, active=True):
    return connection.execute(
        "INSERT INTO goals (owner_id, name, goal_type, category, progress_source, "
        "current_progress_amount_cents, active, created_at, updated_at) "
        "VALUES ('owner-a', 'Progress safeguard', 'SAVINGS', 'FINANCIAL', "
        "?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
        (source, amount, active),
    ).lastrowid


@pytest.fixture(scope="module", params=["migration", "model"])
def goal_progress_database(request, tmp_path_factory):
    path = tmp_path_factory.mktemp("goal-progress") / "goals.db"
    if request.param == "migration":
        result = _alembic(path, "upgrade", "head")
        assert result.returncode == 0, result.stderr
    else:
        engine = create_engine(f"sqlite:///{path}")
        Goal.__table__.create(engine)
        engine.dispose()
    return path


@pytest.mark.parametrize("source", GOAL_PROGRESS_SOURCES)
@pytest.mark.parametrize("amount", [None, 0, 12345, 100_000_000_000_000])
@pytest.mark.parametrize("active", [True, False])
def test_sqlite_raw_progress_insert_and_updates(
    goal_progress_database, source, amount, active,
):
    with sqlite3.connect(goal_progress_database) as connection:
        # Match runtime's legacy FK policy: the CHECK must not depend on it.
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (0,)
        allowed = source == "MANUAL" or amount is None
        if allowed:
            goal_id = _insert_progress(connection, source, amount, active)
            assert connection.execute(
                "SELECT progress_source, current_progress_amount_cents, active "
                "FROM goals WHERE id = ?", (goal_id,),
            ).fetchone() == (source, amount, active)
        else:
            with pytest.raises(sqlite3.IntegrityError, match="ck_goals_manual_progress_only"):
                _insert_progress(connection, source, amount, active)
            goal_id = _insert_progress(connection, "MANUAL", amount, active)
            # A source-only update cannot bypass enforcement.
            with pytest.raises(sqlite3.IntegrityError, match="ck_goals_manual_progress_only"):
                connection.execute(
                    "UPDATE goals SET progress_source = ? WHERE id = ?",
                    (source, goal_id),
                )
            connection.execute(
                "UPDATE goals SET progress_source = ?, "
                "current_progress_amount_cents = NULL WHERE id = ?",
                (source, goal_id),
            )
            # An amount-only update cannot bypass enforcement either.
            with pytest.raises(sqlite3.IntegrityError, match="ck_goals_manual_progress_only"):
                connection.execute(
                    "UPDATE goals SET current_progress_amount_cents = ? WHERE id = ?",
                    (amount, goal_id),
                )
        connection.rollback()


def _goal_snapshot(connection):
    tables = ("goals", "goal_items", "goal_milestones", "goal_checkpoints", "accounts", "debts")
    return {
        table: connection.execute(f"SELECT * FROM {table} ORDER BY id").fetchall()
        for table in tables
    }


def test_progress_migration_preserves_rows_and_sqlite_relationship_guards(tmp_path):
    path = tmp_path / "preserve-progress.db"
    result = _alembic(path, "upgrade", "0022_publish_key_stage")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        _seed_pre_goal_financial_rows(connection)
        goal_id = _insert_progress(connection, "MANUAL", 0)
        _insert_progress(connection, "MANUAL", 100_000_000_000_000, False)
        _insert_progress(connection, "ACCOUNT_BALANCE", None, False)
        for table, column, value in (
            ("goal_items", "name", "Keep item"),
            ("goal_milestones", "title", "Keep milestone"),
            ("goal_checkpoints", "amount_cents", 0),
        ):
            connection.execute(
                f"INSERT INTO {table} (owner_id, goal_id, {column}, created_at, updated_at) "
                "VALUES ('owner-a', ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (goal_id, value),
            )
        connection.commit()
        before = _goal_snapshot(connection)
        triggers = connection.execute(
            "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name"
        ).fetchall()
        indexes = connection.execute("PRAGMA index_list(goals)").fetchall()

    for command in (
        ("upgrade", "head"), ("downgrade", "0022_publish_key_stage"), ("upgrade", "head"),
    ):
        result = _alembic(path, *command)
        assert result.returncode == 0, result.stderr
        with sqlite3.connect(path) as connection:
            assert _goal_snapshot(connection) == before
            current_triggers = connection.execute(
                "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' ORDER BY name"
            ).fetchall()
            original_names = {row[0] for row in triggers}
            assert [row for row in current_triggers if row[0] in original_names] == triggers
            # Additive work guards appear only when the work migration is present.
            expected_extra = {
                f"trg_{table}_owner_{suffix}"
                for table in ("projects", "tasks") for suffix in ("insert", "update")
            } | {
                f"trg_{parent}_restrict_{table}_{suffix}"
                for parent, table in (("goals", "projects"), ("projects", "tasks"))
                for suffix in ("delete", "identity_update")
            }
            assert {row[0] for row in current_triggers} - original_names == (
                expected_extra if command == ("upgrade", "head") else set()
            )
            assert connection.execute("PRAGMA index_list(goals)").fetchall() == indexes
            with pytest.raises(sqlite3.IntegrityError, match="Explicitly remove Goal composition"):
                connection.execute("DELETE FROM goals WHERE id = ?", (goal_id,))
            with pytest.raises(sqlite3.IntegrityError, match="owner must match"):
                connection.execute(
                    "UPDATE goal_items SET owner_id = 'owner-b' WHERE goal_id = ?", (goal_id,),
                )
            connection.rollback()


@pytest.mark.parametrize("amount", [0, 12345])
@pytest.mark.parametrize("active", [True, False])
def test_progress_migration_refuses_historical_conflicts_without_repair(tmp_path, amount, active):
    path = tmp_path / "unsupported-progress.db"
    result = _alembic(path, "upgrade", "0022_publish_key_stage")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        _insert_progress(connection, "ACCOUNT_BALANCE", amount, active)
        connection.commit()
        before = _goal_snapshot(connection)
        schema = connection.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall()
    refused = _alembic(path, "upgrade", "head")
    assert refused.returncode != 0
    assert "preserve records and obtain explicit owner review" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert _goal_snapshot(connection) == before
        assert connection.execute(
            "SELECT name, sql FROM sqlite_master ORDER BY name"
        ).fetchall() == schema
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0022_publish_key_stage",)