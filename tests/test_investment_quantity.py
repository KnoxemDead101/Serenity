"""Investment quantities must fit real holdings (migration 0012)."""

import sqlite3

from sqlalchemy import BigInteger

from models.investment import Investment
from test_migrations import run_alembic


def test_quantity_column_is_64_bit():
    assert isinstance(Investment.__table__.c.quantity_units.type, BigInteger)


def test_large_fractional_quantities_round_trip(client):
    created = client.post("/serenity-api/investments", json={
        "name": "Index Fund", "quantity": "1234.56789012",
        "cost_basis": "100000.00", "current_value": "120000.00",
    })
    assert created.status_code == 201, created.text
    assert created.json()["quantity"] == "1234.56789012"


def test_quantity_above_the_cap_is_rejected(client):
    response = client.post("/serenity-api/investments", json={
        "name": "Too many", "quantity": "1000000000.00000001",
        "cost_basis": "1.00", "current_value": "1.00",
    })
    assert response.status_code == 422
    assert "at most 1,000,000,000" in response.text


def test_0012_upgrades_and_downgrades_on_sqlite_without_touching_rows(tmp_path):
    database_path = tmp_path / "quantity-bigint.db"
    run_alembic(database_path, "upgrade", "0011_identity_and_workspaces")
    connection = sqlite3.connect(database_path)
    now = "2026-09-24 12:00:00"
    connection.execute(
        "INSERT INTO investments (id, owner_id, name, quantity_units, cost_basis_cents, "
        "current_value_cents, active, created_at, updated_at) "
        "VALUES (1, 'w1', 'Fund', 250000000000, 100, 100, 1, ?, ?)",
        (now, now),
    )
    connection.commit()
    connection.close()
    run_alembic(database_path, "upgrade", "head")
    run_alembic(database_path, "downgrade", "0011_identity_and_workspaces")
    run_alembic(database_path, "upgrade", "head")
    connection = sqlite3.connect(database_path)
    try:
        assert connection.execute(
            "SELECT quantity_units FROM investments WHERE id = 1"
        ).fetchone()[0] == 250000000000
    finally:
        connection.close()