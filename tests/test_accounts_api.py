"""
Tests for the account API: the full path from HTTP request to database
and back, the same path the browser uses.
"""

VALID_ACCOUNT = {
    "name": "Everyday Checking",
    "account_type": "Checking",
    "classification": "Personal",
    "opening_balance": "1500.00",
    "institution": "  My Bank  ",
    "notes": "",
}


def test_create_account(client):
    response = client.post("/api/accounts", json=VALID_ACCOUNT)

    assert response.status_code == 201
    body = response.json()
    assert body["id"] == 1
    assert body["name"] == "Everyday Checking"
    assert body["current_balance"] == "1500.00"  # money comes back as a string
    assert body["institution"] == "My Bank"  # spaces stripped
    assert body["notes"] is None  # blank became None


def test_created_account_appears_in_list(client):
    client.post("/api/accounts", json=VALID_ACCOUNT)
    response = client.get("/api/accounts")
    assert response.status_code == 200
    assert [account["name"] for account in response.json()] == ["Everyday Checking"]


def test_get_one_account(client):
    client.post("/api/accounts", json=VALID_ACCOUNT)
    assert client.get("/api/accounts/1").status_code == 200
    assert client.get("/api/accounts/999").status_code == 404


def test_rejects_unknown_account_type(client):
    bad = {**VALID_ACCOUNT, "account_type": "Piggy Bank"}
    response = client.post("/api/accounts", json=bad)
    assert response.status_code == 422
    assert "Account type must be one of" in response.text


def test_rejects_blank_name(client):
    response = client.post("/api/accounts", json={**VALID_ACCOUNT, "name": "   "})
    assert response.status_code == 422


def test_rejects_fractions_of_a_cent(client):
    response = client.post("/api/accounts", json={**VALID_ACCOUNT, "opening_balance": "10.005"})
    assert response.status_code == 422


def test_options_endpoint(client):
    options = client.get("/api/accounts/options").json()
    assert "Checking" in options["account_types"]
    assert "Business" in options["classifications"]


def test_dashboard_summary(client):
    client.post("/api/accounts", json=VALID_ACCOUNT)
    client.post("/api/accounts", json={**VALID_ACCOUNT, "name": "Biz", "classification": "Business",
                                       "opening_balance": "200.50"})
    summary = client.get("/api/dashboard/summary").json()
    assert summary["account_count"] == 2
    assert summary["total_balance"] == "1700.50"
    assert summary["balance_by_classification"]["Business"] == "200.50"
