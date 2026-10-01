"""Browser verification of organizational portfolio UI; no financial side effects."""

from playwright.sync_api import expect


BASE = "http://serenity.test/portfolios"
PORTFOLIOS = "/serenity-api/portfolios"
CONTAINERS = "/serenity-api/investment-accounts"


def account(client, name="Cash ledger"):
    result = client.post("/serenity-api/accounts", json={
        "name": name, "account_type": "Brokerage", "classification": "Investment",
        "opening_balance": "325.00",
    })
    assert result.status_code == 201, result.text
    return result.json()


def create_portfolio(page, name):
    form = page.locator("#portfolio-form")
    form.locator("[name=name]").fill(name)
    form.get_by_role("button", name="Add portfolio").click()
    expect(page.locator("#portfolio-message")).to_have_text("Portfolio added.")


def test_empty_multiple_edit_and_cancel(page, client):
    page.goto(BASE)
    expect(page.get_by_role("heading", name="Portfolios", exact=True)).to_be_visible()
    expect(page.locator("#portfolios-body")).to_contain_text("No portfolios yet.")
    expect(page.locator("#legacy-links")).to_be_hidden()
    assert client.get(PORTFOLIOS).json() == []  # reading does not create defaults
    create_portfolio(page, "Family")
    create_portfolio(page, "Retirement")
    expect(page.locator("#portfolios-body tr")).to_have_count(2)
    row = page.locator("#portfolios-body tr").filter(has_text="Family")
    row.get_by_role("button", name="Edit").click()
    form = page.locator("#portfolio-form")
    form.locator("[name=name]").fill("Unsaved")
    form.get_by_role("button", name="Cancel edit").click()
    expect(form.locator("[name=name]")).to_have_value("")
    expect(row).to_contain_text("Family")
    row.get_by_role("button", name="Edit").click()
    form.locator("[name=notes]").fill("Private organizational group")
    form.get_by_role("button", name="Save portfolio").click()
    expect(row).to_contain_text("Private organizational group")


def test_container_regroup_immutable_account_archive_dependencies(page, client):
    cash = account(client)
    before = client.get("/serenity-api/dashboard/summary").json()
    page.goto(BASE)
    create_portfolio(page, "One")
    create_portfolio(page, "Two")
    portfolios = client.get(PORTFOLIOS).json()
    one = next(record for record in portfolios if record["name"] == "One")
    two = next(record for record in portfolios if record["name"] == "Two")
    created = client.post(CONTAINERS, json={
        "name": "Brokerage group", "portfolio_id": one["id"],
        "account_id": cash["id"], "notes": "Link is metadata",
    })
    assert created.status_code == 201, created.text
    page.reload()
    page.locator("#legacy-links summary").click()
    form = page.locator("#container-form")
    assert client.get("/serenity-api/dashboard/summary").json() == before
    record = client.get(CONTAINERS).json()[0]
    assert record["account_id"] == cash["id"]
    assert record["portfolio_id"] == one["id"]
    expect(form.locator("[name=account_id] option")).to_have_count(1)  # link reserved
    row = page.locator("#containers-body tr").filter(has_text="Brokerage group")
    row.get_by_role("button", name="Edit").click()
    expect(form.locator("[name=account_id]")).to_be_disabled()
    form.locator("[name=portfolio_id]").select_option(str(two["id"]))
    form.locator("[name=notes]").fill("Moved organizational grouping")
    form.get_by_role("button", name="Save container").click()
    expect(row).to_contain_text("Moved organizational grouping")
    assert client.get(f"{CONTAINERS}/{record['id']}").json()["portfolio_id"] == two["id"]
    assert client.get(f"{CONTAINERS}/{record['id']}").json()["account_id"] == cash["id"]
    assert client.get("/serenity-api/dashboard/summary").json() == before

    row_one = page.locator("#portfolios-body tr").filter(has_text="One")
    page.once("dialog", lambda dialog: dialog.dismiss())
    row_one.get_by_role("button", name="Archive").click()
    assert client.get(f"{PORTFOLIOS}/{one['id']}").json()["active"]
    page.once("dialog", lambda dialog: dialog.accept())
    row_one.get_by_role("button", name="Archive").click()
    expect(row_one.get_by_role("button", name="Reactivate")).to_be_visible()
    expect(page.locator("#container-form [name=portfolio_id] option").filter(has_text="One")).to_have_count(0)
    row_two = page.locator("#portfolios-body tr").filter(has_text="Two")
    page.once("dialog", lambda dialog: dialog.accept())
    row_two.get_by_role("button", name="Archive").click()
    expect(page.locator("#portfolio-message")).to_contain_text("Deactivate active investment accounts")
    assert client.get(f"{PORTFOLIOS}/{two['id']}").json()["active"]
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Archive").click()
    expect(row.get_by_role("button", name="Reactivate")).to_be_visible()
    page.once("dialog", lambda dialog: dialog.accept())
    row_two.get_by_role("button", name="Archive").click()
    expect(row_two.get_by_role("button", name="Reactivate")).to_be_visible()
    row.get_by_role("button", name="Reactivate").click()
    expect(page.locator("#container-message")).to_contain_text("Portfolio is inactive")
    row_two.get_by_role("button", name="Reactivate").click()
    expect(row_two.get_by_role("button", name="Archive")).to_be_visible()
    row.get_by_role("button", name="Reactivate").click()
    expect(row.get_by_role("button", name="Archive")).to_be_visible()
    assert client.get("/serenity-api/dashboard/summary").json() == before


def test_failed_save_retains_draft_and_session_recovery_clears_it(page, client):
    account(client)
    created = client.post(PORTFOLIOS, json={"name": "Existing"}).json()
    page.goto(BASE)
    row = page.locator("#portfolios-body tr").filter(has_text="Existing")
    row.get_by_role("button", name="Edit").click()
    form = page.locator("#portfolio-form")
    form.locator("[name=name]").fill("Unsent draft")
    page.route(f"**{PORTFOLIOS}/{created['id']}", lambda route: route.fulfill(
        status=503, content_type="application/json",
        body='{"detail":"Saving is unavailable; try again"}'
    ) if route.request.method == "PUT" else route.continue_())
    form.get_by_role("button", name="Save portfolio").click()
    expect(page.locator("#portfolio-message")).to_have_text("Saving is unavailable; try again")
    expect(form.locator("[name=name]")).to_have_value("Unsent draft")
    assert client.get(f"{PORTFOLIOS}/{created['id']}").json()["name"] == "Existing"
    page.route("**/serenity-api/accounts", lambda route: route.fulfill(
        status=401, content_type="application/json", body='{"detail":"Session ended"}'
    ))
    page.reload()
    expect(page.get_by_role("heading", name="Your session has ended")).to_be_visible()
    expect(page.locator("#portfolio-form")).to_have_count(0)
    expect(page.locator("#portfolios-body")).to_have_count(0)
    expect(page.get_by_text("Existing")).to_have_count(0)