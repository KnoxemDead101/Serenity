"""Goal-only SQLite trigger coverage; never enable SQLite FKs globally."""

import sqlite3

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from storage.database import Base
from test_goal_composition_migration import _alembic, _insert_goal


TABLES = ("goal_items", "goal_milestones", "goal_checkpoints")


def _trigger_names(connection):
    return {
        row[0] for row in _execute(connection,
            "SELECT name FROM sqlite_master WHERE type = 'trigger'"
        )
    }


def _expected_guard_triggers():
    names = set()
    for table in TABLES:
        names.update({
            f"trg_{table}_owner_insert",
            f"trg_{table}_owner_update",
            f"trg_goals_restrict_{table}_delete",
            f"trg_goals_restrict_{table}_identity_update",
        })
    return names


def _financial_schema(connection):
    return {
        row[0]: row[1] for row in _execute(connection,
            "SELECT name, sql FROM sqlite_master "
            "WHERE type = 'table' AND name IN ('accounts', 'debts', 'transactions')"
        )
    }


def _financial_rows(connection):
    return {
        "accounts": _execute(connection,
            "SELECT name, opening_balance_cents, owner_id FROM accounts ORDER BY id"
        ).fetchall(),
        "debts": _execute(connection,
            "SELECT name, balance_cents, owner_id FROM debts ORDER BY id"
        ).fetchall(),
        "transactions": _execute(connection,
            "SELECT description, amount_cents, owner_id FROM transactions ORDER BY id"
        ).fetchall(),
    }


def _execute(connection, statement, parameters=()):
    if hasattr(connection, "exec_driver_sql"):
        return connection.exec_driver_sql(statement, parameters)
    return connection.execute(statement, parameters)


def _integrity_error(connection):
    return IntegrityError if hasattr(connection, "exec_driver_sql") else sqlite3.IntegrityError


def _seed_financial_rows(connection, owner_id):
    now = "2026-10-02 12:00:00"
    _execute(connection,
        "INSERT INTO accounts (name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at, owner_id) "
        "VALUES ('Guard baseline account', 'Checking', 'Personal', 59900, 1, ?, ?, ?)",
        (now, now, owner_id),
    )
    _execute(connection,
        "INSERT INTO debts (name, debt_type, balance_cents, interest_rate_milli, "
        "minimum_payment_cents, active, created_at, updated_at, owner_id) "
        "VALUES ('Guard baseline debt', 'Other', 25000, 0, 100, 1, ?, ?, ?)",
        (now, now, owner_id),
    )
    account_id = _execute(connection,
        "SELECT id FROM accounts WHERE name = 'Guard baseline account'"
    ).fetchone()[0]
    _execute(connection,
        "INSERT INTO transactions (account_id, date, transaction_type, classification, "
        "amount_cents, description, created_at, updated_at, owner_id) "
        "VALUES (?, '2026-10-02', 'Expense', 'Personal', 300, "
        "'Guard baseline transaction', ?, ?, ?)",
        (account_id, now, now, owner_id),
    )


def _child_values(table, owner_id, goal_id):
    values = {
        "owner_id": owner_id,
        "goal_id": goal_id,
        "sort_order": 0,
        "created_at": "2026-10-02 12:00:00",
        "updated_at": "2026-10-02 12:00:00",
    }
    if table == "goal_items":
        values.update(name="Guard item", status="PLANNED", active=1)
    elif table == "goal_milestones":
        values.update(title="Guard milestone", status="NOT_STARTED")
    else:
        values.update(amount_cents=0)
    return values


def _insert_child(connection, table, owner_id, goal_id):
    values = _child_values(table, owner_id, goal_id)
    fields = tuple(values)
    cursor = _execute(connection,
        f"INSERT INTO {table} ({', '.join(fields)}) VALUES "
        f"({', '.join('?' for _ in fields)})",
        tuple(values[field] for field in fields),
    )
    return cursor.lastrowid


def _assert_all_guards_reject_reparenting_and_parent_identity_changes(
    connection, owner_id, goal_id,
):
    """Exercise inserts, owner/Goal updates, and RESTRICT behavior per family."""
    error_type = _integrity_error(connection)
    created = {}
    for table in TABLES:
        created[table] = _insert_child(connection, table, owner_id, goal_id)
        wrong_owner = _child_values(table, "foreign-owner", goal_id)
        fields = tuple(wrong_owner)
        with pytest.raises(error_type, match="Goal composition owner"):
            _execute(connection,
                f"INSERT INTO {table} ({', '.join(fields)}) VALUES "
                f"({', '.join('?' for _ in fields)})",
                tuple(wrong_owner[field] for field in fields),
            )
        wrong_goal = _child_values(table, owner_id, goal_id + 100_000)
        with pytest.raises(error_type, match="Goal composition owner"):
            fields = tuple(wrong_goal)
            _execute(connection,
                f"INSERT INTO {table} ({', '.join(fields)}) VALUES "
                f"({', '.join('?' for _ in fields)})",
                tuple(wrong_goal[field] for field in fields),
            )
        with pytest.raises(error_type, match="Goal composition owner"):
            _execute(connection,
                f"UPDATE {table} SET owner_id = 'foreign-owner' WHERE id = ?",
                (created[table],),
            )
        with pytest.raises(error_type, match="Goal composition owner"):
            _execute(connection,
                f"UPDATE {table} SET goal_id = ? WHERE id = ?",
                (goal_id + 100_000, created[table]),
            )
        assert _execute(connection,
            f"SELECT owner_id, goal_id FROM {table} WHERE id = ?",
            (created[table],),
        ).fetchone() == (owner_id, goal_id)

    with pytest.raises(
        error_type, match="Explicitly remove Goal composition",
    ):
        _execute(connection, "DELETE FROM goals WHERE id = ?", (goal_id,))
    with pytest.raises(
        error_type, match="Cannot change the identity of a Goal",
    ):
        _execute(connection,
            "UPDATE goals SET owner_id = 'foreign-owner' WHERE id = ?", (goal_id,),
        )
    with pytest.raises(
        error_type, match="Cannot change the identity of a Goal",
    ):
        _execute(connection,
            "UPDATE goals SET id = id + 100000 WHERE id = ?", (goal_id,),
        )
    assert _execute(connection,
        "SELECT owner_id, name FROM goals WHERE id = ?", (goal_id,),
    ).fetchone() == (owner_id, "Guard parent")

    for table in TABLES:
        _execute(connection, f"DELETE FROM {table} WHERE id = ?", (created[table],))
    _execute(connection, "DELETE FROM goals WHERE id = ?", (goal_id,))
    assert _execute(connection,
        "SELECT COUNT(*) FROM goals WHERE id = ?", (goal_id,),
    ).fetchone()[0] == 0


def test_metadata_create_all_installs_only_goal_guards_and_preserves_financial_schema(
    tmp_path,
):
    engine = create_engine(f"sqlite:///{tmp_path / 'metadata-guards.db'}")
    Base.metadata.create_all(bind=engine)
    try:
        with engine.begin() as connection:
            assert connection.scalar(text("PRAGMA foreign_keys")) == 0
            _seed_financial_rows(connection, "guard-owner")
            financial_schema = _financial_schema(connection)
            financial_rows = _financial_rows(connection)
            goal_id = connection.execute(text(
                "INSERT INTO goals (owner_id, name, goal_type, category, status, "
                "priority, progress_source, active, created_at, updated_at) "
                "VALUES ('guard-owner', 'Guard parent', 'SAVINGS', 'FINANCIAL', "
                "'NOT_STARTED', 'NORMAL', 'MANUAL', 1, CURRENT_TIMESTAMP, "
                "CURRENT_TIMESTAMP)"
            )).lastrowid
            _assert_all_guards_reject_reparenting_and_parent_identity_changes(
                connection, "guard-owner", goal_id,
            )
            assert connection.scalar(text("PRAGMA foreign_keys")) == 0
            assert _trigger_names(connection) == _expected_guard_triggers()
            assert _financial_schema(connection) == financial_schema
            assert _financial_rows(connection) == financial_rows
    finally:
        engine.dispose()


def test_alembic_guards_reject_invalid_tuples_and_safe_downgrade_removes_them(
    tmp_path,
):
    path = tmp_path / "migration-guards.db"
    previous = _alembic(path, "upgrade", "0018_goal_core")
    assert previous.returncode == 0, previous.stderr
    with sqlite3.connect(path) as connection:
        preserved_goal_id = _insert_goal(connection)
        _seed_financial_rows(connection, "owner-a")
        financial_schema = _financial_schema(connection)
        financial_rows = _financial_rows(connection)

    # Isolate this feature's non-invasive-schema contract. Later conversion
    # migrations intentionally add financial parent keys and separate guards.
    upgraded = _alembic(path, "upgrade", "0019_goal_composition")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        assert _trigger_names(connection) == _expected_guard_triggers()
        assert _financial_schema(connection) == financial_schema
        assert _financial_rows(connection) == financial_rows
        guard_goal_id = _insert_goal(connection)
        connection.execute(
            "UPDATE goals SET name = 'Guard parent' WHERE id = ?",
            (guard_goal_id,),
        )
        _assert_all_guards_reject_reparenting_and_parent_identity_changes(
            connection, "owner-a", guard_goal_id,
        )
        assert _financial_schema(connection) == financial_schema
        assert _financial_rows(connection) == financial_rows
        connection.commit()

    downgraded = _alembic(path, "downgrade", "0018_goal_core")
    assert downgraded.returncode == 0, downgraded.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone()[0] == 0
        assert _trigger_names(connection).isdisjoint(_expected_guard_triggers())
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0018_goal_core",)
        assert connection.execute(
            "SELECT name FROM goals WHERE id = ?", (preserved_goal_id,)
        ).fetchone() == ("Preserved goal",)
        assert _financial_schema(connection) == financial_schema
        assert _financial_rows(connection) == financial_rows