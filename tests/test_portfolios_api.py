"""Owner isolation and financially neutral, archival portfolio metadata."""

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from auth import require_session
from main import app
from models.portfolio import InvestmentAccount
from services.dashboard_service import get_dashboard_summary
from services.export_service import build_export


ROOT = "/serenity-api"


def _post(client, path, data):
    result = client.post(ROOT + path, json=data)
    assert result.status_code == 201, result.text
    return result.json()


def _account(client, name="Cash"):
    return _post(client, "/accounts", {
        "name": name, "account_type": "Brokerage",
        "classification": "Personal", "opening_balance": "120.00",
    })


def test_organization_is_private_and_does_not_change_financial_totals(client, db):
    cash = _account(client)
    _post(client, "/investments", {
        "name": "Original", "quantity": "1.25", "cost_basis": "10",
        "current_value": "15",
    })
    before = get_dashboard_summary(db, "test-owner")
    legacy = build_export(db, "test-owner")["investments"]
    empty = _post(client, "/portfolios", {"name": "  Child account  "})
    assert empty["name"] == "Child account"
    assert empty["notes"] is None
    second = _post(client, "/portfolios", {"name": "Child account"})
    container = _post(client, "/investment-accounts", {
        "name": "  Brokerage sleeve  ", "portfolio_id": empty["id"],
        "account_id": cash["id"], "notes": " grouping only ",
    })
    assert container["name"] == "Brokerage sleeve"
    assert container["notes"] == "grouping only"
    assert not any(k in container for k in ("balance", "current_value", "opening_balance"))
    assert client.put(ROOT + f"/investment-accounts/{container['id']}", json={
        "name": "Renamed", "portfolio_id": second["id"], "account_id": cash["id"],
    }).status_code == 200
    after = get_dashboard_summary(db, "test-owner")
    assert after == before
    export = client.get(ROOT + "/export").json()
    assert export["format_version"] == 7
    assert export["investments"] == legacy
    assert export["accounts"][0]["opening_balance_cents"] == 12000
    assert [p["id"] for p in export["portfolios"]] == [empty["id"], second["id"]]
    assert export["investment_accounts"][0]["portfolio_id"] == second["id"]
    assert export["investment_accounts"][0]["account_id"] == cash["id"]
    assert client.get(ROOT + "/export/transactions.csv").status_code == 200


def test_lifecycle_immutable_link_and_inactive_parents(client):
    cash = _account(client)
    other = _account(client, "Second")
    portfolio = _post(client, "/portfolios", {"name": "Mine"})
    target = _post(client, "/portfolios", {"name": "Target"})
    payload = {"name": "Sleeve", "portfolio_id": portfolio["id"], "account_id": cash["id"]}
    container = _post(client, "/investment-accounts", payload)
    url = ROOT + f"/investment-accounts/{container['id']}"
    assert client.post(ROOT + f"/portfolios/{portfolio['id']}/deactivate").status_code == 409
    assert client.put(url, json={**payload, "account_id": other["id"]}).status_code == 422
    assert client.post(ROOT + "/investment-accounts", json=payload).status_code == 409
    assert client.post(url + "/deactivate").json()["active"] is False
    assert client.post(ROOT + "/investment-accounts", json=payload).status_code == 409
    assert client.post(ROOT + f"/portfolios/{portfolio['id']}/deactivate").json()["active"] is False
    assert client.post(url + "/reactivate").status_code == 409
    assert client.put(url, json={**payload, "name": "Archived, renamed"}).status_code == 200
    assert client.put(url, json={**payload, "portfolio_id": target["id"]}).status_code == 200
    assert client.post(url + "/reactivate").json()["active"] is True
    assert client.post(ROOT + f"/accounts/{cash['id']}/deactivate").status_code == 200
    assert client.get(url).status_code == 200
    assert client.put(url, json={**payload, "portfolio_id": target["id"]}).status_code == 200
    assert client.post(url + "/deactivate").status_code == 200
    assert client.post(url + "/reactivate").status_code == 409
    assert client.post(ROOT + "/investment-accounts", json={
        **payload, "account_id": cash["id"]
    }).status_code == 409
    backup = client.get(ROOT + "/export").json()
    assert backup["investment_accounts"][0]["active"] is False


def test_owner_scoping_parent_injection_and_validation(client, db):
    own = _post(client, "/portfolios", {"name": "Own"})
    account = _account(client)
    own_container = _post(client, "/investment-accounts", {
        "name": "Own sleeve", "portfolio_id": own["id"], "account_id": account["id"],
    })
    app.dependency_overrides[require_session] = lambda: "other-owner"
    foreign_portfolio = _post(client, "/portfolios", {"name": "Other"})
    foreign_account = _account(client, "Other cash")
    foreign_container = _post(client, "/investment-accounts", {
        "name": "Other sleeve", "portfolio_id": foreign_portfolio["id"],
        "account_id": foreign_account["id"],
    })
    assert [p["id"] for p in client.get(ROOT + "/portfolios").json()] == [foreign_portfolio["id"]]
    assert [p["id"] for p in client.get(ROOT + "/investment-accounts").json()] == [foreign_container["id"]]
    for path in (f"/portfolios/{own['id']}", f"/investment-accounts/{own_container['id']}"):
        assert client.get(ROOT + path).status_code == 404
        payload = {"name": "No", "notes": "bad"}
        if path.startswith("/investment-accounts/"):
            payload.update(portfolio_id=foreign_portfolio["id"], account_id=foreign_account["id"])
        assert client.put(ROOT + path, json=payload).status_code == 404
        for action in ("deactivate", "reactivate"):
            assert client.post(ROOT + path + "/" + action).status_code == 404
    assert client.post(ROOT + "/investment-accounts", json={
        "name": "Wrong owner portfolio", "portfolio_id": own["id"],
        "account_id": foreign_account["id"],
    }).status_code == 404
    assert client.post(ROOT + "/investment-accounts", json={
        "name": "Wrong owner cash", "portfolio_id": foreign_portfolio["id"],
        "account_id": account["id"],
    }).status_code == 404
    assert client.put(ROOT + f"/investment-accounts/{foreign_container['id']}", json={
        "name": "Wrong owner portfolio", "portfolio_id": own["id"],
        "account_id": foreign_account["id"],
    }).status_code == 404
    assert client.put(ROOT + f"/investment-accounts/{foreign_container['id']}", json={
        "name": "Wrong owner cash", "portfolio_id": foreign_portfolio["id"],
        "account_id": account["id"],
    }).status_code == 404
    export = client.get(ROOT + "/export").json()
    assert [row["id"] for row in export["portfolios"]] == [foreign_portfolio["id"]]
    assert [row["id"] for row in export["investment_accounts"]] == [foreign_container["id"]]
    app.dependency_overrides[require_session] = lambda: "test-owner"
    assert client.get(ROOT + f"/investment-accounts/{own_container['id']}").json()["name"] == "Own sleeve"
    assert len(client.get(ROOT + "/investment-accounts").json()) == 1
    assert client.post(ROOT + "/portfolios", json={"name": " "}).status_code == 422
    assert client.post(ROOT + "/portfolios", json={"name": "x" * 101}).status_code == 422
    assert client.post(ROOT + "/portfolios", json={"name": "valid", "notes": "x" * 1001}).status_code == 422
    assert client.post(ROOT + "/portfolios", json={"name": "valid", "owner_id": "other-owner"}).status_code == 422
    assert client.delete(ROOT + f"/portfolios/{own['id']}").status_code == 405
    assert client.delete(ROOT + f"/investment-accounts/{own_container['id']}").status_code == 405


def test_composite_foreign_keys_reject_bypassed_cross_owner_links(client, db):
    own = _post(client, "/portfolios", {"name": "Own"})
    own_account = _account(client)
    app.dependency_overrides[require_session] = lambda: "other-owner"
    foreign = _post(client, "/portfolios", {"name": "Other"})
    foreign_account = _account(client, "Other cash")
    # SQLite does not enable FK checking by default in this fixture. Enable
    # it before the direct bypass inserts on the same DB-API connection.
    db.rollback()
    db.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    for portfolio_id, account_id in (
        (own["id"], foreign_account["id"]),
        (foreign["id"], own_account["id"]),
    ):
        row = InvestmentAccount(
            owner_id="other-owner", name="Invalid", portfolio_id=portfolio_id,
            account_id=account_id,
        )
        db.add(row)
        with pytest.raises(IntegrityError):
            db.commit()
        db.rollback()
    assert db.scalar(text("SELECT count(*) FROM investment_accounts")) == 0
