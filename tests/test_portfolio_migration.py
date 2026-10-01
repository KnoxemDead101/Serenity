"""Only disposable SQLite files are migrated by these checks."""

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


def test_additive_upgrade_and_non_destructive_downgrade(tmp_path):
    path = tmp_path / "portfolio-only.db"
    base = _alembic(path, "upgrade", "0014_instrument_registry")
    assert base.returncode == 0, base.stderr
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO accounts (id, owner_id, name, account_type, classification, "
            "opening_balance_cents, active, created_at, updated_at) VALUES "
            "(1, 'owner-one', 'Keep', 'Brokerage', 'Personal', 98765, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO investments (id, owner_id, name, quantity_units, "
            "cost_basis_cents, current_value_cents, active, created_at, updated_at) "
            "VALUES (1, 'owner-one', 'Keep', 125000000, 1200, 1500, 1, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    upgraded = _alembic(path, "upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT opening_balance_cents FROM accounts WHERE id = 1"
        ).fetchone() == (98765,)
        assert connection.execute(
            "SELECT quantity_units, cost_basis_cents, current_value_cents "
            "FROM investments WHERE id = 1"
        ).fetchone() == (125000000, 1200, 1500)
        assert connection.execute(
            "SELECT name FROM sqlite_master WHERE name='ux_accounts_owner_id_id'"
        ).fetchone()
        connection.execute(
            "INSERT INTO portfolios (id, owner_id, name, active, created_at, updated_at) "
            "VALUES (1, 'owner-one', 'Saved', 0, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    refused = _alembic(path, "downgrade", "0014_instrument_registry")
    assert refused.returncode != 0
    assert "Cannot downgrade 0015" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0015_portfolio_containers",)
        assert connection.execute("SELECT name FROM portfolios").fetchone() == ("Saved",)
        connection.execute("DELETE FROM portfolios")
    allowed = _alembic(path, "downgrade", "0014_instrument_registry")
    assert allowed.returncode == 0, allowed.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT opening_balance_cents FROM accounts").fetchone() == (98765,)
        assert connection.execute("SELECT current_value_cents FROM investments").fetchone() == (1500,)
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='ux_accounts_owner_id_id'").fetchone() is None
        assert connection.execute("SELECT name FROM sqlite_master WHERE name='portfolios'").fetchone() is None


def test_direct_portfolio_upgrade_preserves_legacy_and_refuses_populated_downgrade(tmp_path):
    path = tmp_path / "portfolio-direct.db"
    assert _alembic(path, "upgrade", "0016_investment_review_drafts").returncode == 0
    with sqlite3.connect(path) as connection:
        connection.execute(
            "INSERT INTO portfolios (id, owner_id, name, active, created_at, updated_at) "
            "VALUES (1, 'owner-one', 'Investments', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
        connection.execute(
            "INSERT INTO investments (id, owner_id, name, quantity_units, cost_basis_cents, "
            "current_value_cents, active, review_pending, created_at, updated_at) "
            "VALUES (1, 'owner-one', 'Unchanged legacy', 100000000, 900, 1000, 1, 0, "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)"
        )
    result = _alembic(path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT portfolio_id, review_pending, current_value_cents FROM investments WHERE id=1"
        ).fetchone() == (None, 0, 1000)
        connection.execute(
            "UPDATE investments SET portfolio_id=1, review_pending=1 WHERE id=1"
        )
    refused = _alembic(path, "downgrade", "0016_investment_review_drafts")
    assert refused.returncode != 0
    assert "Cannot downgrade 0017" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute(
            "SELECT portfolio_id, current_value_cents FROM investments WHERE id=1"
        ).fetchone() == (1, 1000)