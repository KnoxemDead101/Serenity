"""API tests for full edits and soft-deactivation of financial records."""

import pytest

ACCOUNT = {
    "name": "Checking", "account_type": "Checking",
    "classification": "Personal", "opening_balance": "100.00",
}
BILL = {"name": "Rent", "amount": "1200.00", "due_date": "2026-10-01", "frequency": "Monthly"}
DEBT = {"name": "Card", "debt_type": "Credit Card", "balance": "500.00",
        "interest_rate": "6.875", "minimum_payment": "25.00"}
INVESTMENT = {"name": "Index fund", "ticker": "vti", "quantity": "2.5",
              "cost_basis": "400.00", "current_value": "450.00"}


def create(client, path, body):
    response = client.post(f"/serenity-api/{path}", json=body)
    assert response.status_code == 201, response.text
    return response.json()


def summary(client):
    return client.get("/serenity-api/dashboard/summary").json()


def test_edit_account_recalculates_balance(client):
    account = create(client, "accounts", ACCOUNT)
    client.post(f"/serenity-api/accounts/{account['id']}/transactions", json={
        "date": "2026-09-23", "transaction_type": "Expense",
        "amount": "10.00", "description": "Groceries",
    })
    response = client.put(f"/serenity-api/accounts/{account['id']}", json={
        **ACCOUNT, "name": " Everyday Checking ", "opening_balance": "150.00",
    })
    assert response.status_code == 200
    assert response.json()["name"] == "Everyday Checking"
    assert response.json()["current_balance"] == "140.00"


def test_deactivated_account_still_counts_and_rejects_new_transactions(client):
    account = create(client, "accounts", ACCOUNT)
    url = f"/serenity-api/accounts/{account['id']}"
    response = client.post(f"{url}/deactivate")
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert summary(client)["net_worth"] == "100.00"
    blocked = client.post(f"{url}/transactions", json={
        "date": "2026-09-23", "transaction_type": "Income",
        "amount": "5.00", "description": "Blocked",
    })
    assert blocked.status_code == 422
    assert "deactivated" in blocked.json()["detail"]
    assert client.post(f"{url}/reactivate").json()["active"] is True


@pytest.mark.parametrize(
    "path,body,count_field,total_field,total_before",
    [
        ("bills", BILL, "bill_count", "monthly_bill_total", "1200.00"),
        ("debts", DEBT, "debt_count", "debt_balance", "500.00"),
        ("investments", INVESTMENT, "investment_count", "investment_value", "450.00"),
    ],
)
def test_deactivated_finance_records_leave_totals(
    client, path, body, count_field, total_field, total_before
):
    record = create(client, path, body)
    assert record["active"] is True
    assert summary(client)[count_field] == 1
    assert summary(client)[total_field] == total_before
    response = client.post(f"/serenity-api/{path}/{record['id']}/deactivate")
    assert response.status_code == 200
    assert response.json()["active"] is False
    assert summary(client)[count_field] == 0
    assert summary(client)[total_field] == "0.00"
    assert client.post(f"/serenity-api/{path}/{record['id']}/reactivate").status_code == 200


def test_finance_edits_are_full_replacements(client):
    bill = create(client, "bills", BILL)
    edited = client.put(
        f"/serenity-api/bills/{bill['id']}",
        json={**BILL, "amount": "300.00", "frequency": "Quarterly"},
    )
    assert edited.status_code == 200
    assert edited.json()["amount"] == "300.00"
    assert summary(client)["monthly_bill_total"] == "100.00"


@pytest.mark.parametrize("path", ["accounts", "bills", "debts", "investments"])
def test_unknown_lifecycle_records_are_404(client, path):
    assert client.post(f"/serenity-api/{path}/999/deactivate").status_code == 404
    assert client.post(f"/serenity-api/{path}/999/reactivate").status_code == 404