from decimal import Decimal

import pytest
from pydantic import ValidationError

from schemas.transaction import TransactionCreate


def test_record_and_list_transactions_updates_account_and_dashboard(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Checking", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "10.10",
    }).json()
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    expense = client.post(url, json={
        "date": "2026-09-21", "transaction_type": "Expense",
        "amount": "3.25", "description": " Lunch ", "category": " Food ",
    })
    assert expense.status_code == 201
    assert expense.json()["amount"] == "3.25"
    assert expense.json()["description"] == "Lunch"
    assert expense.json()["category"] == "Food"
    income = client.post(url, json={
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "0.15", "description": "Refund",
    })
    assert income.status_code == 201
    assert [item["description"] for item in client.get(url).json()] == ["Refund", "Lunch"]
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()["current_balance"] == "7.00"
    assert client.get("/serenity-api/dashboard/summary").json()["total_balance"] == "7.00"


@pytest.mark.parametrize("field,value", [
    ("amount", "0"), ("amount", "-2.00"), ("amount", "1.005"),
    ("transaction_type", "Transfer"), ("transaction_type", "Deposit"),
    ("transaction_type", "Withdrawal"), ("classification", "Savings"),
    ("description", "   "),
    ("date", "not-a-date"), ("category", "x" * 101),
])
def test_invalid_transaction_input_is_rejected(client, field, value):
    account = client.post("/serenity-api/accounts", json={
        "name": "Cash", "account_type": "Cash", "classification": "Personal",
    }).json()
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    body = {
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "1.00", "description": "Income",
    }
    body[field] = value
    assert client.post(url, json=body).status_code == 422
    assert client.get(url).json() == []


def test_classification_defaults_to_the_account(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Business", "account_type": "Checking",
        "classification": "Business",
    }).json()
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    created = client.post(url, json={
        "date": "2026-09-22", "transaction_type": "Expense",
        "amount": "40.00", "description": "Shipping labels",
    }).json()
    assert created["classification"] == "Business"


def test_classification_can_differ_from_account(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Personal", "account_type": "Checking",
        "classification": "Personal",
    }).json()
    response = client.post(
        f"/serenity-api/accounts/{account['id']}/transactions",
        json={
            "date": "2026-09-22", "transaction_type": "Expense",
            "amount": "89.99", "description": "SSD",
            "classification": "Business", "merchant": " Newegg ",
            "location": "Online", "subcategory": "Storage",
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["classification"] == "Business"
    assert body["merchant"] == "Newegg"
    assert body["location"] == "Online"
    assert body["subcategory"] == "Storage"


def test_transaction_options_endpoint(client):
    options = client.get("/serenity-api/transactions/options").json()
    assert options["transaction_types"] == ["Income", "Expense"]
    assert "Business" in options["classifications"]
    assert "Business Equipment" in options["categories"]


def test_nonexistent_account_transactions_return_404(client):
    url = "/serenity-api/accounts/999/transactions"
    assert client.get(url).status_code == 404
    assert client.post(url, json={
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "1.00", "description": "Income",
    }).status_code == 404


def test_update_transaction_changes_balance_and_dashboard_total(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Checking", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "100.00",
    }).json()
    collection_url = f"/serenity-api/accounts/{account['id']}/transactions"
    transaction = client.post(collection_url, json={
        "date": "2026-09-20", "transaction_type": "Expense",
        "amount": "10.00", "description": "Wrong purchase",
    }).json()

    response = client.put(f"{collection_url}/{transaction['id']}", json={
        "date": "2026-09-21", "transaction_type": "Income",
        "amount": "25.50", "description": " Corrected refund ",
        "category": " Refunds ",
    })

    assert response.status_code == 200
    assert response.json()["description"] == "Corrected refund"
    assert response.json()["category"] == "Refunds"
    assert response.json()["amount"] == "25.50"
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()["current_balance"] == "125.50"
    assert client.get("/serenity-api/dashboard/summary").json()["total_balance"] == "125.50"


def test_delete_transaction_restores_balance_and_removes_history(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Savings", "account_type": "Savings",
        "classification": "Personal", "opening_balance": "50.00",
    }).json()
    collection_url = f"/serenity-api/accounts/{account['id']}/transactions"
    transaction = client.post(collection_url, json={
        "date": "2026-09-22", "transaction_type": "Expense",
        "amount": "12.34", "description": "Duplicate",
    }).json()

    response = client.delete(f"{collection_url}/{transaction['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(collection_url).json() == []
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()["current_balance"] == "50.00"
    assert client.get("/serenity-api/dashboard/summary").json()["total_balance"] == "50.00"


def test_transaction_cannot_be_changed_through_another_account(client):
    first = client.post("/serenity-api/accounts", json={
        "name": "First", "account_type": "Checking", "classification": "Personal",
    }).json()
    second = client.post("/serenity-api/accounts", json={
        "name": "Second", "account_type": "Savings", "classification": "Personal",
    }).json()
    transaction = client.post(
        f"/serenity-api/accounts/{first['id']}/transactions",
        json={
            "date": "2026-09-22", "transaction_type": "Income",
            "amount": "5.00", "description": "Income",
        },
    ).json()
    wrong_url = f"/serenity-api/accounts/{second['id']}/transactions/{transaction['id']}"
    replacement = {
        "date": "2026-09-22", "transaction_type": "Expense",
        "amount": "999.00", "description": "Not allowed",
    }

    assert client.put(wrong_url, json=replacement).status_code == 404
    assert client.delete(wrong_url).status_code == 404
    assert client.get(f"/serenity-api/accounts/{first['id']}").json()["current_balance"] == "5.00"
    assert client.get(f"/serenity-api/accounts/{second['id']}").json()["current_balance"] == "0.00"


def test_invalid_update_leaves_transaction_unchanged(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Cash", "account_type": "Cash", "classification": "Personal",
    }).json()
    collection_url = f"/serenity-api/accounts/{account['id']}/transactions"
    transaction = client.post(collection_url, json={
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "3.00", "description": "Tips",
    }).json()

    invalid = {**transaction, "amount": "0"}
    assert client.put(f"{collection_url}/{transaction['id']}", json=invalid).status_code == 422
    assert client.get(collection_url).json()[0]["amount"] == "3.00"
    assert client.get(
        f"/serenity-api/accounts/{account['id']}/transaction-corrections"
    ).json() == []


def test_each_edit_and_delete_keeps_a_read_only_snapshot(client, db):
    account = client.post("/serenity-api/accounts", json={
        "name": "Journal", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "20.00",
    }).json()
    other = client.post("/serenity-api/accounts", json={
        "name": "Other", "account_type": "Savings", "classification": "Business",
    }).json()
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    history_url = f"/serenity-api/accounts/{account['id']}/transaction-corrections"
    transaction = client.post(url, json={
        "date": "2026-09-20", "transaction_type": "Expense",
        "amount": "1.01", "description": "Original", "category": "First",
    }).json()
    item_url = f"{url}/{transaction['id']}"
    first_edit = client.put(item_url, json={
        "date": "2026-09-21", "transaction_type": "Income",
        "amount": "2.02", "description": "Revised", "category": "Second",
    })
    assert first_edit.status_code == 200
    second_edit = client.put(item_url, json={
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "3.03", "description": "Final", "category": "",
    })
    assert second_edit.status_code == 200
    assert client.get(url).json()[0]["description"] == "Final"
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()["current_balance"] == "23.03"

    assert client.delete(item_url).status_code == 204
    assert client.get(url).json() == []
    assert client.put(item_url, json={
        "date": "2026-09-23", "transaction_type": "Income",
        "amount": "9.99", "description": "Resurrect",
    }).status_code == 404
    assert client.delete(item_url).status_code == 404
    history = client.get(history_url).json()
    assert [event["action"] for event in reversed(history)] == [
        "Updated", "Updated", "Deleted",
    ]
    assert [event["before"]["amount"] for event in reversed(history)] == [
        "1.01", "2.02", "3.03",
    ]
    assert [event["after"]["amount"] if event["after"] else None
            for event in reversed(history)] == ["2.02", "3.03", None]
    assert [event["before"]["description"] for event in reversed(history)] == [
        "Original", "Revised", "Final",
    ]
    assert all(event["changed_at"] and event["transaction_id"] == transaction["id"]
               for event in history)
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()["current_balance"] == "20.00"
    summary = client.get("/serenity-api/dashboard/summary").json()
    assert summary["total_balance"] == "20.00"
    assert summary["balance_by_classification"]["Personal"] == "20.00"
    assert client.get(f"/serenity-api/accounts/{other['id']}/transaction-corrections").json() == []
    assert client.get("/serenity-api/accounts/999/transaction-corrections").status_code == 404
    assert client.put(history_url, json={}).status_code == 405
    assert client.delete(f"{history_url}/{history[0]['id']}").status_code == 404

    from models.transaction import Transaction
    from models.transaction_correction import TransactionCorrection

    assert db.get(Transaction, transaction["id"]).deleted_at is not None
    assert db.query(TransactionCorrection).count() == 3


def test_old_snapshots_without_new_fields_still_display(client, db):
    from models.transaction_correction import TransactionCorrection

    account = client.post("/serenity-api/accounts", json={
        "name": "Checking", "account_type": "Checking",
        "classification": "Personal",
    }).json()
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    transaction = client.post(url, json={
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "1.00", "description": "Now",
    }).json()
    db.add(TransactionCorrection(
        account_id=account["id"], transaction_id=transaction["id"], action="Updated",
        before={"date": "2026-09-01", "transaction_type": "Deposit",
                "amount_cents": 100, "description": "Then", "category": None},
        after={"date": "2026-09-22", "transaction_type": "Deposit",
               "amount_cents": 100, "description": "Now", "category": None},
    ))
    db.commit()
    event = client.get(
        f"/serenity-api/accounts/{account['id']}/transaction-corrections"
    ).json()[0]
    assert event["before"]["transaction_type"] == "Deposit"
    assert event["before"]["merchant"] is None


def test_transaction_money_uses_decimal_not_float():
    data = TransactionCreate(
        date="2026-09-22", transaction_type="Income",
        amount=Decimal("0.01"), description="Penny",
    )
    assert data.amount == Decimal("0.01")
    with pytest.raises(ValidationError):
        TransactionCreate(
            date="2026-09-22", transaction_type="Income",
            amount=Decimal("0.001"), description="Fraction",
        )