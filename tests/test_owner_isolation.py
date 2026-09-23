"""Every invited user sees only their own financial records."""

import pytest

from auth import AUTH_COOKIE, issue_session
from conftest import sign_in_as


def test_financial_records_and_exports_are_scoped_to_session_owner(real_auth_client):
    client = real_auth_client
    assert not hasattr(client.app.state, "auth_bypass")
    try:
        client.cookies.set(AUTH_COOKIE, issue_session("owner-a", "fixture-owner-a"))
        account = client.post("/serenity-api/accounts", json={
            "name": "A Checking", "account_type": "Checking",
            "classification": "Personal", "opening_balance": "100.00",
        }).json()
        transaction = client.post(
            f"/serenity-api/accounts/{account['id']}/transactions",
            json={
                "date": "2026-09-23", "transaction_type": "Expense",
                "amount": "10.00", "description": "Owner A purchase",
            },
        ).json()
        business = client.post(
            "/serenity-api/businesses", json={"name": "A Business"}
        ).json()
        dependent = client.post(
            "/serenity-api/dependents", json={"display_name": "A Dependent"}
        ).json()
        bill = client.post("/serenity-api/bills", json={
            "name": "A Bill", "amount": "25.00",
            "due_date": "2026-10-01",
        }).json()
        debt = client.post("/serenity-api/debts", json={
            "name": "A Debt", "debt_type": "Credit Card",
            "balance": "50.00",
        }).json()
        investment = client.post("/serenity-api/investments", json={
            "name": "A Investment", "cost_basis": "40.00",
            "current_value": "45.00",
        }).json()

        client.cookies.set(AUTH_COOKIE, issue_session("owner-b", "fixture-owner-b"))
        assert client.get("/serenity-api/accounts").json() == []
        assert client.get("/serenity-api/bills").json() == []
        assert client.get("/serenity-api/debts").json() == []
        assert client.get("/serenity-api/investments").json() == []
        assert client.get("/serenity-api/businesses").json() == []
        options = client.get("/serenity-api/transactions/options").json()
        assert options["businesses"] == []
        assert options["dependents"] == []
        assert client.get("/serenity-api/dashboard/summary").json()["account_count"] == 0
        assert client.get(
            f"/serenity-api/accounts/{account['id']}"
        ).status_code == 404
        assert client.get(
            f"/serenity-api/accounts/{account['id']}/transactions"
        ).status_code == 404
        assert client.get(f"/serenity-api/bills/{bill['id']}").status_code == 404
        assert client.get(f"/serenity-api/debts/{debt['id']}").status_code == 404
        assert client.get(
            f"/serenity-api/investments/{investment['id']}"
        ).status_code == 404
        assert client.put(
            f"/serenity-api/accounts/{account['id']}/transactions/{transaction['id']}",
            json={
                "date": "2026-09-23", "transaction_type": "Expense",
                "amount": "1.00", "description": "Unauthorized edit",
            },
        ).status_code == 404
        assert client.delete(
            f"/serenity-api/accounts/{account['id']}/transactions/{transaction['id']}"
        ).status_code == 404

        backup = client.get("/serenity-api/export").json()
        assert backup["accounts"] == []
        assert backup["transactions"] == []
        assert backup["businesses"] == []
        assert backup["dependents"] == []
        assert backup["bills"] == []
        assert backup["debts"] == []
        assert backup["investments"] == []
        assert client.get(
            "/serenity-api/export/transactions.csv"
        ).text.count("\n") == 1

        client.cookies.set(AUTH_COOKIE, issue_session("owner-a", "fixture-owner-a"))
        assert client.get("/serenity-api/accounts").json()[0]["id"] == account["id"]
        assert client.get(
            f"/serenity-api/accounts/{account['id']}/transactions"
        ).json()[0]["id"] == transaction["id"]
        assert client.get("/serenity-api/businesses").json()[0]["id"] == business["id"]
    finally:
        client.cookies.clear()


@pytest.fixture
def owner_a_records(real_auth_client):
    """Seed a complete owner-A dataset, then return as owner B."""
    client = real_auth_client
    sign_in_as(client, "owner-a")
    account = client.post("/serenity-api/accounts", json={
        "name": "A Checking", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "100.00",
    }).json()
    transaction = client.post(
        f"/serenity-api/accounts/{account['id']}/transactions",
        json={"date": "2026-09-23", "transaction_type": "Expense",
              "amount": "10.00", "description": "Owner A purchase"},
    ).json()
    records = {
        "account": account,
        "transaction": transaction,
        "business": client.post("/serenity-api/businesses", json={"name": "A Business"}).json(),
        "dependent": client.post("/serenity-api/dependents", json={
            "display_name": "A Dependent",
        }).json(),
    }
    sign_in_as(client, "owner-b")
    return client, records


def test_other_owner_cannot_read_or_mutate_business_dependents_or_transactions(owner_a_records):
    client, records = owner_a_records
    account_id = records["account"]["id"]
    transaction_id = records["transaction"]["id"]
    business_id = records["business"]["id"]
    dependent_id = records["dependent"]["id"]

    assert client.get("/serenity-api/businesses").json() == []
    assert client.get("/serenity-api/dependents").json() == []
    assert client.put(
        f"/serenity-api/accounts/{account_id}/transactions/{transaction_id}",
        json={"date": "2026-09-23", "transaction_type": "Expense",
              "amount": "1.00", "description": "Hijacked"},
    ).status_code == 404
    assert client.put(f"/serenity-api/businesses/{business_id}", json={
        "name": "Hijacked",
    }).status_code == 404
    assert client.put(f"/serenity-api/dependents/{dependent_id}", json={
        "display_name": "Hijacked",
    }).status_code == 404

    other_account = client.post("/serenity-api/accounts", json={
        "name": "B Checking", "account_type": "Checking",
        "classification": "Personal",
    }).json()
    payload = {
        "date": "2026-09-23", "transaction_type": "Expense",
        "amount": "2.00", "description": "Cross-owner link",
        "business_id": business_id,
    }
    blocked = client.post(
        f"/serenity-api/accounts/{other_account['id']}/transactions", json=payload
    )
    assert blocked.status_code == 422
    assert "doesn't exist" in blocked.json()["detail"]


def test_other_owner_exports_and_dashboard_are_isolated(owner_a_records):
    client, records = owner_a_records
    backup = client.get("/serenity-api/export").json()
    assert backup["accounts"] == []
    assert backup["transactions"] == []
    assert backup["businesses"] == []
    assert backup["dependents"] == []
    assert client.get("/serenity-api/dashboard/summary").json()["account_count"] == 0
    sign_in_as(client, "owner-a")
    assert client.get(
        f"/serenity-api/accounts/{records['account']['id']}"
    ).json()["name"] == "A Checking"