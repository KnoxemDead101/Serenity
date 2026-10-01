"""Permanent removal of standalone finance records; accounts keep their history."""

import pytest

from conftest import sign_in_as
from models.bill import Bill
from models.debt import Debt
from models.investment import Investment


RECORDS = [
    ("bills", Bill, {
        "name": "Rent", "amount": "1200.00", "due_date": "2026-10-01",
        "frequency": "Monthly",
    }, "bill_count", "monthly_bill_total"),
    ("debts", Debt, {
        "name": "Card", "debt_type": "Credit Card", "balance": "500.00",
        "minimum_payment": "25.00",
    }, "debt_count", "debt_balance"),
    ("investments", Investment, {
        "name": "Fund", "quantity": "2.5", "cost_basis": "400.00",
        "current_value": "450.00",
    }, "investment_count", "investment_value"),
]


def create(client, path, payload):
    response = client.post(f"/serenity-api/{path}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("path,model,payload,count,total", RECORDS)
@pytest.mark.parametrize("inactive", [False, True])
def test_deletion_is_permanent_and_scoped(
    real_auth_client, db, path, model, payload, count, total, inactive
):
    client = real_auth_client
    sign_in_as(client, "owner-a")
    account = create(client, "accounts", {
        "name": "Checking", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "100.00",
    })
    transaction = create(
        client, f"accounts/{account['id']}/transactions", {
            "date": "2026-09-23", "transaction_type": "Expense",
            "amount": "10.00", "description": "Groceries",
        }
    )
    a_record = create(client, path, payload)
    url = f"/serenity-api/{path}/{a_record['id']}"
    if inactive:
        assert client.post(f"{url}/deactivate").status_code == 200
    assert db.get(model, a_record["id"]) is not None

    sign_in_as(client, "owner-b")
    b_record = create(client, path, {**payload, "name": "Other owner's record"})
    assert client.delete(url).status_code == 404
    assert db.get(model, a_record["id"]) is not None
    assert client.get(f"/serenity-api/{path}/{b_record['id']}").status_code == 200

    client.cookies.clear()
    assert client.delete(url).status_code == 401
    assert db.get(model, a_record["id"]) is not None

    sign_in_as(client, "owner-a")
    removed = client.delete(url)
    assert removed.status_code == 204
    assert removed.content == b""
    db.expire_all()
    assert db.get(model, a_record["id"]) is None
    assert client.get(url).status_code == 404
    assert client.delete(url).status_code == 404
    assert client.post(f"{url}/reactivate").status_code == 404
    assert client.get(f"/serenity-api/{path}").json() == []
    assert client.get("/serenity-api/export").json()[path] == []
    summary = client.get("/serenity-api/finance/summary").json()
    assert summary[count] == 0
    assert summary[total] == "0.00"
    dashboard = client.get("/serenity-api/dashboard/summary").json()
    assert dashboard[count] == 0
    assert dashboard["net_worth"] == "90.00"
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()[
        "current_balance"
    ] == "90.00"
    assert client.get(
        f"/serenity-api/accounts/{account['id']}/transactions"
    ).json()[0]["id"] == transaction["id"]
    assert client.get("/serenity-api/export").json()["transactions"][0][
        "id"
    ] == transaction["id"]

    sign_in_as(client, "owner-b")
    assert client.get(f"/serenity-api/{path}/{b_record['id']}").status_code == 200
    assert client.get("/serenity-api/finance/summary").json()[count] == 1
    assert client.get("/serenity-api/export").json()[path][0]["id"] == b_record["id"]