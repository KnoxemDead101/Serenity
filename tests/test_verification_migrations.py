"""Additive SQLite evidence schema and refusal to discard retained checks."""

import sqlite3

import pytest

from test_system_history import sqlite_alembic


def test_additive_migration_constraints_and_preservation(tmp_path):
    path = tmp_path / "verification.db"
    assert sqlite_alembic(path, "upgrade", "0026_system_observations").returncode == 0
    with sqlite3.connect(path) as connection:
        before = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        connection.execute(
            "INSERT INTO debts (owner_id,name,debt_type,balance_cents,interest_rate_milli,"
            "minimum_payment_cents,active,created_at,updated_at) "
            "VALUES ('owner','Synthetic','Other',123,0,0,1,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
        original = connection.execute("SELECT * FROM debts").fetchall()
    result = sqlite_alembic(path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        after = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert after - before == {"manual_verifications"}
        assert connection.execute("SELECT * FROM debts").fetchall() == original
        connection.execute(
            "INSERT INTO manual_verifications (owner_id,kind,target_id,snapshot,as_of,evidence,recorded_at) "
            "VALUES ('owner','debt_balance',1,?,CURRENT_DATE,'Synthetic evidence',CURRENT_TIMESTAMP)",
            ("a" * 64,),
        )
        for change in ("kind='unknown'", "evidence=''", "target_id=0", "snapshot='bad'"):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute("UPDATE manual_verifications SET " + change)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO manual_verifications SELECT NULL,owner_id,kind,target_id,snapshot,as_of,evidence,"
                "recorded_at FROM manual_verifications"
            )
    refused = sqlite_alembic(path, "downgrade", "0026_system_observations")
    assert refused.returncode != 0
    assert "Cannot downgrade while manual verification evidence exists" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM manual_verifications").fetchone()[0] == 1
        connection.execute("DELETE FROM manual_verifications")
    assert sqlite_alembic(path, "downgrade", "0026_system_observations").returncode == 0