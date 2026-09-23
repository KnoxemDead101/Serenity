"""Tests for complete JSON backups and transaction CSV exports."""

import csv
import io


def seed(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Checking", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "100.10",
    }).json()
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    kept = client.post(url, json={
        "date": "2026-09-23", "transaction_type": "Expense",
        "amount": "12.34", "description": "Groceries, weekly",
        "merchant": "Fry's",
    }).json()
    removed = client.post(url, json={
        "date": "2026-09-22", "transaction_type": "Income",
        "amount": "5.00", "description": "Duplicate",
    }).json()
    client.delete(f"{url}/{removed['id']}")
    client.post("/serenity-api/bills", json={
        "name": "Internet", "amount": "70.00",
        "due_date": "2026-09-25", "frequency": "Monthly",
    })
    client.post("/serenity-api/debts", json={
        "name": "Card", "debt_type": "Credit Card",
        "balance": "250.00", "interest_rate": "6.875",
    })
    client.post("/serenity-api/investments", json={
        "name": "Fund", "quantity": "0.5", "cost_basis": "10.00",
        "current_value": "11.00",
    })
    return account, kept, removed


def test_json_backup_contains_everything(client):
    account, kept, removed = seed(client)
    response = client.get("/serenity-api/export")
    assert response.status_code == 200
    backup = response.json()
    assert backup["format"] == "serenity-backup"
    assert backup["accounts"][0]["opening_balance_cents"] == 10010
    by_id = {t["id"]: t for t in backup["transactions"]}
    assert by_id[kept["id"]]["deleted_at"] is None
    assert by_id[removed["id"]]["deleted_at"] is not None
    assert backup["debts"][0]["interest_rate_milli"] == 6875
    assert backup["investments"][0]["quantity_units"] == 50_000_000


def test_money_is_never_a_float(client):
    seed(client)
    def walk(value):
        if isinstance(value, float):
            raise AssertionError(f"float found in backup: {value}")
        if isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
    walk(client.get("/serenity-api/export").json())


def test_transactions_csv_and_formula_neutralization(client):
    account, _, _ = seed(client)
    url = f"/serenity-api/accounts/{account['id']}/transactions"
    client.post(url, json={
        "date": "2026-09-24", "transaction_type": "Expense",
        "amount": "1.00", "description": " =SUM(A1:A2)",
        "merchant": "+unsafe",
    })
    response = client.get("/serenity-api/export/transactions.csv")
    assert response.status_code == 200
    rows = list(csv.DictReader(io.StringIO(response.text)))
    row = next(row for row in rows if "SUM" in row["description"])
    assert row["description"].startswith("'")
    assert row["merchant"].startswith("'")
    assert next(row for row in rows if row["description"] == "Groceries, weekly")["deleted"] == "no"


def test_empty_export_still_works(client):
    backup = client.get("/serenity-api/export").json()
    assert backup["accounts"] == [] and backup["transactions"] == []
    rows = list(csv.reader(io.StringIO(client.get("/serenity-api/export/transactions.csv").text)))
    assert rows[0][0] == "id" and len(rows) == 1