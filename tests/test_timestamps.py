"""Regression tests for UTC timestamps in SQLite-backed API responses."""


def assert_utc(value: str) -> None:
    assert value.endswith("+00:00") or value.endswith("Z")


def test_account_timestamp_is_explicitly_utc(client):
    response = client.post(
        "/serenity-api/accounts",
        json={
            "name": "UTC Checking",
            "account_type": "Checking",
            "classification": "Personal",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert_utc(body["created_at"])
    assert_utc(body["updated_at"])


def test_finance_timestamps_are_explicitly_utc(client):
    bill = client.post(
        "/serenity-api/bills",
        json={
            "name": "Rent",
            "amount": "1200.00",
            "due_date": "2026-10-01",
            "frequency": "Monthly",
        },
    )
    debt = client.post(
        "/serenity-api/debts",
        json={"name": "Card", "debt_type": "Credit Card", "balance": "10.00"},
    )
    investment = client.post(
        "/serenity-api/investments",
        json={
            "name": "Index fund",
            "quantity": "1",
            "cost_basis": "10.00",
            "current_value": "11.00",
        },
    )

    for response in (bill, debt, investment):
        assert response.status_code == 201
        body = response.json()
        assert_utc(body["created_at"])
        assert_utc(body["updated_at"])


def test_transaction_and_correction_timestamps_are_explicitly_utc(client):
    account = client.post(
        "/serenity-api/accounts",
        json={
            "name": "History Checking",
            "account_type": "Checking",
            "classification": "Personal",
        },
    ).json()
    collection = f"/serenity-api/accounts/{account['id']}/transactions"
    transaction = client.post(
        collection,
        json={
            "date": "2026-09-23",
            "transaction_type": "Income",
            "amount": "1.00",
            "description": "Initial",
        },
    )
    assert transaction.status_code == 201
    body = transaction.json()
    assert_utc(body["created_at"])
    assert_utc(body["updated_at"])

    updated = client.put(
        f"{collection}/{body['id']}",
        json={
            "date": "2026-09-23",
            "transaction_type": "Income",
            "amount": "2.00",
            "description": "Updated",
        },
    )
    assert updated.status_code == 200
    corrections = client.get(
        f"/serenity-api/accounts/{account['id']}/transaction-corrections"
    )
    assert corrections.status_code == 200
    assert_utc(corrections.json()[0]["changed_at"])