"""API coverage for business/dependent labels and transaction links."""


def post(client, path, body):
    return client.post(f"/serenity-api/{path}", json=body)


def account(client):
    return post(client, "accounts", {
        "name": "Checking", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "500.00",
    }).json()


def test_business_and_dependent_lifecycle(client):
    business = post(client, "businesses", {"name": "  KTT  ", "notes": ""})
    dependent = post(client, "dependents", {"display_name": "Child 1"})
    assert business.status_code == dependent.status_code == 201
    assert business.json()["name"] == "KTT"
    assert business.json()["notes"] is None
    assert dependent.json()["active"] is True
    assert client.post(f"/serenity-api/businesses/{business.json()['id']}/deactivate").json()["active"] is False
    assert client.post(f"/serenity-api/dependents/{dependent.json()['id']}/deactivate").json()["active"] is False


def test_names_are_case_insensitively_unique(client):
    first = post(client, "businesses", {"name": "KTT"})
    duplicate = post(client, "businesses", {"name": "ktt"})
    assert first.status_code == 201
    assert duplicate.status_code == 409


def test_links_set_business_classification_and_preserve_history(client):
    owner = account(client)
    business = post(client, "businesses", {"name": "KTT"}).json()
    dependent = post(client, "dependents", {"display_name": "Child 1"}).json()
    response = client.post(
        f"/serenity-api/accounts/{owner['id']}/transactions",
        json={
            "date": "2026-09-23", "transaction_type": "Expense",
            "amount": "25.00", "description": "Purchase",
            "business_id": business["id"], "dependent_id": dependent["id"],
        },
    )
    assert response.status_code == 201
    assert response.json()["classification"] == "Business"
    assert response.json()["business_name"] == "KTT"
    assert response.json()["dependent_name"] == "Child 1"
    update = client.put(
        f"/serenity-api/accounts/{owner['id']}/transactions/{response.json()['id']}",
        json={
            "date": "2026-09-23", "transaction_type": "Expense",
            "amount": "30.00", "description": "Updated",
            "business_id": business["id"], "dependent_id": dependent["id"],
        },
    )
    assert update.status_code == 200
    history = client.get(
        f"/serenity-api/accounts/{owner['id']}/transaction-corrections"
    ).json()
    assert history[0]["before"]["business_name"] == "KTT"


def test_inactive_labels_are_not_options_or_new_links(client):
    owner = account(client)
    business = post(client, "businesses", {"name": "Old"}).json()
    client.post(f"/serenity-api/businesses/{business['id']}/deactivate")
    options = client.get("/serenity-api/transactions/options").json()
    assert options["businesses"] == []
    response = client.post(
        f"/serenity-api/accounts/{owner['id']}/transactions",
        json={
            "date": "2026-09-23", "transaction_type": "Expense",
            "amount": "1.00", "description": "Blocked",
            "business_id": business["id"],
        },
    )
    assert response.status_code == 422