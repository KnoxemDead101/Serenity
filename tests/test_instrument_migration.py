"""Migration creates only additive tables; populated rollback is refused."""

import os
import sqlite3
import subprocess
import sys


def _alembic(path, *args):
    return subprocess.run(
        [sys.executable, "-m", "alembic", *args],
        env={**os.environ, "DATABASE_URL": f"sqlite:///{path}"},
        text=True, capture_output=True,
    )


def test_0014_additive_and_safe_rollback(tmp_path):
    path = tmp_path / "isolated.db"
    base = _alembic(path, "upgrade", "0013_money_bigint")
    assert base.returncode == 0, base.stderr
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO investments "
            "(name, owner_id, quantity_units, current_value_cents, cost_basis_cents, "
            "created_at, updated_at, active) "
            "VALUES ('preserved', 'owner', 14739200, 1200, 1000, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)"
        )
    upgrade = _alembic(path, "upgrade", "0014_instrument_registry")
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(instrument_specifications)")
        }
        assert {"tick_size_units", "point_value_units", "version", "owner_id"} <= columns
        assert connection.execute(
            "SELECT name, quantity_units, current_value_cents FROM investments"
        ).fetchone() == ("preserved", 14739200, 1200)
        connection.execute(
            "INSERT INTO instruments (id, owner_id, symbol, active, created_at, updated_at) "
            "VALUES (1, 'owner', 'MES', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    denied = _alembic(path, "downgrade", "0013_money_bigint")
    assert denied.returncode != 0
    assert "Cannot downgrade 0014" in denied.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone()[0] == "0014_instrument_registry"
        assert connection.execute("SELECT symbol FROM instruments").fetchone()[0] == "MES"
        connection.execute("DELETE FROM instruments")
    allowed = _alembic(path, "downgrade", "0013_money_bigint")
    assert allowed.returncode == 0, allowed.stderr
    with sqlite3.connect(path) as connection:
        assert not connection.execute(
            "SELECT name FROM sqlite_master WHERE name='instruments'"
        ).fetchall()
        assert connection.execute("SELECT name FROM investments").fetchone()[0] == "preserved"