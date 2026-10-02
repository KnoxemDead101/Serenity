"""Instrument metadata is isolated, versioned and never posted as an asset."""

from decimal import Decimal

import pytest

from conftest import sign_in_as
from models.instrument import Instrument, InstrumentSpecification
from services import export_service, instrument_service


FUTURE = {
    "symbol": "MES", "name": "Micro E-mini S&P 500",
    "asset_type": "FUTURE", "exchange": "CME", "currency": "USD",
    "tick_size": "0.25", "point_value": "5",
}
MINI = {
    **FUTURE, "symbol": "ES", "name": "E-mini S&P 500",
    "point_value": "50",
}


def test_registry_versions_export_and_financial_totals_unchanged(client, db):
    original_summary = client.get("/serenity-api/dashboard").json()
    created = client.post("/serenity-api/instruments", json=FUTURE)
    assert created.status_code == 201, created.text
    data = created.json()
    assert data["symbol"] == "MES"
    assert Decimal(str(data["point_value"])) == Decimal("5")
    assert Decimal(str(data["tick_size"])) == Decimal("0.25")
    assert data["version"] == 1
    assert data["active"] is True
    assert client.get("/serenity-api/instruments").json() == [data]

    update = client.put(f"/serenity-api/instruments/{data['id']}", json={
        **FUTURE, "name": "Revised Micro", "point_value": "5.25",
    })
    assert update.status_code == 200, update.text
    revised = update.json()
    assert revised["version"] == 2
    assert revised["specification_id"] != data["specification_id"]
    history = client.get(
        f"/serenity-api/instruments/{data['id']}/specifications"
    ).json()
    assert [item["version"] for item in history] == [1, 2]
    assert history[0]["name"] == FUTURE["name"]
    assert Decimal(str(history[0]["point_value"])) == Decimal("5")
    assert client.post(
        f"/serenity-api/instruments/{data['id']}/deactivate"
    ).json()["active"] is False
    assert client.get(
        f"/serenity-api/instruments/{data['id']}/specifications"
    ).json() == [
        {**item, "active": False, "updated_at": client.get(
            f"/serenity-api/instruments/{data['id']}"
        ).json()["updated_at"]} for item in history
    ]
    assert client.post(
        f"/serenity-api/instruments/{data['id']}/reactivate"
    ).json()["active"] is True
    exported = export_service.build_export(db, "test-owner")
    assert exported["format_version"] == 7
    assert exported["instruments"][0]["symbol"] == "MES"
    assert [s["point_value_units"] for s in exported["instrument_specifications"]] == [
        500_000_000, 525_000_000
    ]
    assert all(not isinstance(value, float) for spec in exported["instrument_specifications"]
               for value in spec.values())
    assert client.get("/serenity-api/dashboard").json() == original_summary
    assert client.get("/serenity-api/finance/summary").json()["investment_count"] == 0


@pytest.mark.parametrize("payload", [
    {**FUTURE, "tick_size": "0.000000001"},
    {**FUTURE, "point_value": "1000000001"},
    {**FUTURE, "currency": "EUR"},
    {**FUTURE, "asset_type": "OPTION"},
    {"symbol": "ES", "name": "Misleading defaults", "asset_type": "FUTURE"},
    {"symbol": "AAPL", "name": "Apple", "asset_type": "STOCK", "point_value": "10"},
])
def test_bad_instrument_inputs_rejected(client, payload):
    assert client.post("/serenity-api/instruments", json=payload).status_code == 422
    assert client.get("/serenity-api/instruments").json() == []


def test_workspace_duplicate_and_cross_owner_access(client, real_auth_client, db):
    # real_auth_client clears test dependency overrides; both sessions below
    # use the signed fixture cookie checked by the auth layer.
    sign_in_as(real_auth_client, "owner-a")
    first = real_auth_client.post("/serenity-api/instruments", json=FUTURE)
    assert first.status_code == 201, first.text
    i = first.json()
    assert real_auth_client.post("/serenity-api/instruments", json={
        **FUTURE, "symbol": " mes ",
    }).status_code == 409
    assert real_auth_client.put(f"/serenity-api/instruments/{i['id']}", json={
        **FUTURE, "symbol": "ES",
    }).status_code == 422
    assert real_auth_client.put(f"/serenity-api/instruments/{i['id']}", json={
        **FUTURE, "asset_type": "STOCK", "point_value": "1",
    }).status_code == 422

    real_auth_client.cookies.clear()
    assert real_auth_client.get("/serenity-api/instruments").status_code == 401
    assert real_auth_client.post("/serenity-api/profit-engine/calculate", json={
        "specification_id": i["specification_id"], "direction": "LONG",
        "quantity": "1", "entry_price": "5000",
    }).status_code == 401
    sign_in_as(real_auth_client, "owner-b")
    assert real_auth_client.get("/serenity-api/instruments").json() == []
    assert real_auth_client.get("/serenity-api/export").json()["instruments"] == []
    for path in (
        f"/serenity-api/instruments/{i['id']}",
        f"/serenity-api/instruments/{i['id']}/specifications",
    ):
        assert real_auth_client.get(path).status_code == 404
    for method, path in (
        ("put", f"/serenity-api/instruments/{i['id']}"),
        ("post", f"/serenity-api/instruments/{i['id']}/deactivate"),
        ("post", f"/serenity-api/instruments/{i['id']}/reactivate"),
    ):
        result = getattr(real_auth_client, method)(path, json=FUTURE if method == "put" else None)
        assert result.status_code == 404
    denied = real_auth_client.post("/serenity-api/profit-engine/calculate", json={
        "specification_id": i["specification_id"], "direction": "LONG",
        "quantity": "1", "entry_price": "5000",
    })
    assert denied.status_code == 404
    assert real_auth_client.post("/serenity-api/instruments", json=FUTURE).status_code == 201
    assert len(db.query(Instrument).all()) == 2
    assert len(db.query(InstrumentSpecification).all()) == 2


def test_owner_required_on_service_and_version_is_immutable(db):
    with pytest.raises(TypeError):
        instrument_service.list_instruments(db)
    with pytest.raises(ValueError):
        instrument_service.list_instruments(db, " ")


def test_historical_calculator_uses_requested_owned_specification(client):
    micro = client.post("/serenity-api/instruments", json=FUTURE).json()
    mini = client.post("/serenity-api/instruments", json=MINI).json()
    request = {
        "direction": "LONG", "quantity": "2",
        "entry_price": "5000", "exit_price": "5001",
        "stop_price": "4999", "fees": "1.00",
    }
    old = client.post("/serenity-api/profit-engine/calculate", json={
        **request, "specification_id": micro["specification_id"],
    })
    assert old.status_code == 200, old.text
    assert Decimal(old.json()["gross_pnl"]) == 10
    assert Decimal(old.json()["net_pnl"]) == 9
    assert Decimal(old.json()["ticks"]) == 4
    assert Decimal(old.json()["risk_dollars"]) == 10
    assert Decimal(client.post("/serenity-api/profit-engine/calculate", json={
        **request, "specification_id": mini["specification_id"],
    }).json()["gross_pnl"]) == 100
    newer = client.put(f"/serenity-api/instruments/{micro['id']}", json={
        **FUTURE, "point_value": "6",
    }).json()
    client.post(f"/serenity-api/instruments/{micro['id']}/deactivate")
    historic = client.post("/serenity-api/profit-engine/calculate", json={
        **request, "specification_id": micro["specification_id"],
    })
    assert Decimal(historic.json()["gross_pnl"]) == 10
    updated = client.post("/serenity-api/profit-engine/calculate", json={
        **request, "specification_id": newer["specification_id"],
    })
    assert Decimal(updated.json()["gross_pnl"]) == 12
