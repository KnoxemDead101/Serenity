def test_finance_records_appear_in_summary(client):
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
        json={
            "name": "Rewards card",
            "debt_type": "Credit Card",
            "balance": "5000.00",
            "interest_rate": "6.875",
            "minimum_payment": "150.00",
        },
    )
    investment = client.post(
        "/serenity-api/investments",
        json={
            "name": "Index fund",
            "ticker": "VTI",
            "quantity": "3.5",
            "cost_basis": "600.00",
            "current_value": "720.00",
        },
    )

    assert bill.status_code == 201
    assert debt.status_code == 201
    assert investment.status_code == 201

    summary = client.get("/serenity-api/dashboard/summary")
    assert summary.status_code == 200
    assert summary.json()["bill_count"] == 1
    assert summary.json()["monthly_bill_total"] == "1200.00"
    assert summary.json()["debt_balance"] == "5000.00"
    assert summary.json()["investment_value"] == "720.00"
    assert summary.json()["net_worth"] == "-4280.00"

    for path, record in (
        ("bills", bill),
        ("debts", debt),
        ("investments", investment),
    ):
        detail = client.get(f"/serenity-api/{path}/{record.json()['id']}")
        assert detail.status_code == 200
        assert detail.json()["name"] == record.json()["name"]
        assert client.get(f"/serenity-api/{path}/999999").status_code == 404

    debt_record = client.get("/serenity-api/debts").json()[0]
    assert debt_record["debt_type"] == "Credit Card"
    assert debt_record["interest_rate"] == "6.875"