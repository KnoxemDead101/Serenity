"""Real PostgreSQL registry and rollback checks on a private disposable cluster.

Reuse the existing socket-only test fixture. Never read the ambient DATABASE_URL,
connect to a running application database, or modify non-registry baseline rows.
"""

from decimal import Decimal

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from services.export_service import build_export
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401


MICRO = {
    "symbol": "MES", "name": "Micro E-mini S&P 500",
    "asset_type": "FUTURE", "exchange": "CME", "currency": "USD",
    "tick_size": "0.25", "point_value": "5",
}


def test_postgres_registry_versions_export_and_safe_rollback(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "head")
    inspector = inspect(pg_engine)
    assert {"instruments", "instrument_specifications"} <= set(inspector.get_table_names())
    columns = {
        column["name"]: column for column in inspector.get_columns("instrument_specifications")
    }
    assert columns["tick_size_units"]["type"].__class__.__name__ == "BIGINT"
    assert columns["point_value_units"]["type"].__class__.__name__ == "BIGINT"
    assert {"ix_instruments_owner_id"} <= {
        index["name"] for index in inspector.get_indexes("instruments")
    }

    # This preexisting domain row must survive both the new upgrade and the
    # subsequent registry-only downgrade on the disposable database.
    account_response = pg_client.post("/serenity-api/accounts", json={
        "name": "Keep this savings account", "account_type": "Savings",
        "classification": "Personal", "opening_balance": "123.45",
    })
    assert account_response.status_code == 201, account_response.text
    account_id = account_response.json()["id"]
    created_response = pg_client.post("/serenity-api/instruments", json=MICRO)
    assert created_response.status_code == 201, created_response.text
    created = created_response.json()
    instrument_id = created["id"]
    first_spec_id = created["specification_id"]
    assert created["version"] == 1

    revision_response = pg_client.put(
        f"/serenity-api/instruments/{instrument_id}",
        json={**MICRO, "name": "Revised micro", "point_value": "6.25"},
    )
    assert revision_response.status_code == 200, revision_response.text
    current = revision_response.json()
    assert current["version"] == 2
    assert current["specification_id"] != first_spec_id
    detail = pg_client.get(f"/serenity-api/instruments/{instrument_id}")
    assert detail.status_code == 200
    assert detail.json()["specification_id"] == current["specification_id"]
    history = pg_client.get(
        f"/serenity-api/instruments/{instrument_id}/specifications"
    )
    assert history.status_code == 200, history.text
    assert [spec["version"] for spec in history.json()] == [1, 2]
    assert [Decimal(spec["point_value"]) for spec in history.json()] == [
        Decimal("5"), Decimal("6.25")
    ]
    with pg_engine.connect() as connection:
        rows = connection.execute(text(
            "SELECT version, tick_size_units, point_value_units "
            "FROM instrument_specifications WHERE instrument_id = :instrument_id "
            "ORDER BY version"
        ), {"instrument_id": instrument_id}).all()
    assert rows == [(1, 25_000_000, 500_000_000), (2, 25_000_000, 625_000_000)]

    for specification_id, expected_gross in (
        (first_spec_id, "10.00"),
        (current["specification_id"], "12.50"),
    ):
        calculation = pg_client.post("/serenity-api/profit-engine/calculate", json={
            "specification_id": specification_id,
            "direction": "LONG", "quantity": "2",
            "entry_price": "5000.00", "exit_price": "5001.00",
        })
        assert calculation.status_code == 200, calculation.text
        assert Decimal(calculation.json()["gross_pnl"]) == Decimal(expected_gross)

    with Session(pg_engine) as db:
        exported = build_export(db, "postgres-money-test")
        other_owner = build_export(db, "other-workspace")
        assert exported["format_version"] == 7
        assert [entry["version"] for entry in exported["instrument_specifications"]] == [1, 2]
        assert [entry["point_value_units"] for entry in exported["instrument_specifications"]] == [
            500_000_000, 625_000_000
        ]
        assert exported["instruments"][0]["id"] == instrument_id
        assert other_owner["instruments"] == []
        assert other_owner["instrument_specifications"] == []

    # The downgrade must refuse populated registry tables without losing
    # instrument history, other finance rows, or the Alembic revision.
    _alembic(postgres_url, "downgrade", "0014_instrument_registry")
    refused = _alembic(postgres_url, "downgrade", "0013_money_bigint", succeeds=False)
    assert "Cannot downgrade 0014" in refused.stderr
    with pg_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014_instrument_registry"
        assert connection.scalar(text(
            "SELECT COUNT(*) FROM instrument_specifications "
            "WHERE instrument_id = :instrument_id"
        ), {"instrument_id": instrument_id}) == 2
        assert connection.scalar(text(
            "SELECT opening_balance_cents FROM accounts WHERE id = :id"
        ), {"id": account_id}) == 12345

    # Explicitly remove only this test's registry rows, then prove empty
    # registry tables can be downgraded without touching the baseline account.
    with pg_engine.begin() as connection:
        connection.execute(text(
            "DELETE FROM instrument_specifications WHERE instrument_id = :id"
        ), {"id": instrument_id})
        connection.execute(text(
            "DELETE FROM instruments WHERE id = :id"
        ), {"id": instrument_id})
    _alembic(postgres_url, "downgrade", "0013_money_bigint")
    assert "instruments" not in inspect(pg_engine).get_table_names()
    assert "instrument_specifications" not in inspect(pg_engine).get_table_names()
    with pg_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0013_money_bigint"
        assert connection.scalar(text(
            "SELECT opening_balance_cents FROM accounts WHERE id = :id"
        ), {"id": account_id}) == 12345
