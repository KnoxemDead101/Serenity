"""Goal Composition migration coverage uses isolated SQLite files only."""

import os
import sqlite3
import subprocess
import sys

import pytest


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


def _insert_goal(connection):
    cursor = connection.execute(
        "INSERT INTO goals (owner_id, name, goal_type, category, status, "
        "priority, progress_source, active, created_at, updated_at) "
        "VALUES ('owner-a', 'Preserved goal', 'SAVINGS', 'FINANCIAL', "
        "'NOT_STARTED', 'NORMAL', 'MANUAL', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
    )
    return cursor.lastrowid


def test_0019_upgrade_adds_only_composition_tables_and_preserves_existing_rows(
    tmp_path,
):
    path = tmp_path / "composition-additive.db"
    previous = _alembic(path, "upgrade", "0018_goal_core")
    assert previous.returncode == 0, previous.stderr
    with sqlite3.connect(path) as connection:
        goal_id = _insert_goal(connection)
        connection.execute(
            "INSERT INTO accounts (name, account_type, classification, "
            "opening_balance_cents, active, created_at, updated_at, owner_id) "
            "VALUES ('Preserve account', 'Checking', 'Personal', 59900, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'owner-a')"
        )
        connection.commit()
        before = _tables(connection)

    upgraded = _alembic(path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        assert _tables(connection) == before | {
            "reconciliation_approvals", "opening_positions",
            "valuation_eligibility", "cash_reconciliation_entries",
            "conversion_events",
            "goal_items", "goal_milestones", "goal_checkpoints",
        }
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0024_restore_publish_keys",)
        assert connection.execute(
            "SELECT name FROM goals WHERE id = ?", (goal_id,)
        ).fetchone() == ("Preserved goal",)
        assert connection.execute(
            "SELECT name, opening_balance_cents, owner_id FROM accounts"
        ).fetchone() == ("Preserve account", 59900, "owner-a")


@pytest.mark.parametrize("table", [
    "goal_items", "goal_milestones", "goal_checkpoints",
])
def test_composition_downgrade_refuses_each_nonempty_child_table_before_dropping(
    tmp_path, table,
):
    path = tmp_path / f"composition-{table}.db"
    upgraded = _alembic(path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        goal_id = _insert_goal(connection)
        columns = {
            row[1] for row in connection.execute(f"PRAGMA table_info({table})")
        }
        base = {
            "owner_id": "owner-a",
            "goal_id": goal_id,
            "sort_order": 0,
            "created_at": "2026-10-01 12:00:00",
            "updated_at": "2026-10-01 12:00:00",
        }
        if table == "goal_items":
            base.update(name="Retain", status="PLANNED", active=1)
        elif table == "goal_milestones":
            base.update(title="Retain", status="NOT_STARTED")
        else:
            base.update(amount_cents=0)
        keys = [key for key in base if key in columns]
        connection.execute(
            f"INSERT INTO {table} ({', '.join(keys)}) VALUES "
            f"({', '.join('?' for _ in keys)})",
            [base[key] for key in keys],
        )
        connection.commit()
        before_tables = _tables(connection)

    refused = _alembic(path, "downgrade", "0018_goal_core")
    assert refused.returncode != 0
    assert "Cannot downgrade Goal Composition" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert set(connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall()) == {
            ("0017_conversion_guards",), ("0019_goal_composition",),
        }
        assert _tables(connection) == before_tables
        assert connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 1
        assert connection.execute(
            "SELECT name FROM goals WHERE id = ?", (goal_id,)
        ).fetchone() == ("Preserved goal",)


def test_empty_child_downgrade_preserves_parent_goals_and_financial_rows(tmp_path):
    path = tmp_path / "composition-empty-downgrade.db"
    previous = _alembic(path, "upgrade", "0018_goal_core")
    assert previous.returncode == 0, previous.stderr
    with sqlite3.connect(path) as connection:
        goal_id = _insert_goal(connection)
        connection.commit()
    upgraded = _alembic(path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        tables = _tables(connection)
        assert {"goal_items", "goal_milestones", "goal_checkpoints"} <= tables
    downgraded = _alembic(path, "downgrade", "0018_goal_core")
    assert downgraded.returncode == 0, downgraded.stderr
    with sqlite3.connect(path) as connection:
        assert set(connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchall()) == {
            ("0017_conversion_guards",), ("0018_goal_core",),
        }
        assert not {"goal_items", "goal_milestones", "goal_checkpoints"} & _tables(
            connection
        )
        assert connection.execute(
            "SELECT name FROM goals WHERE id = ?", (goal_id,)
        ).fetchone() == ("Preserved goal",)