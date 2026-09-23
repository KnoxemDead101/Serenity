"""Exercise the real Accounts page in Chromium against the in-memory test API."""

import shutil
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture
def page(client):
    executable = shutil.which("chromium")
    if executable is None:
        pytest.fail("Chromium is required for Accounts browser tests")

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=executable, headless=True, args=["--no-sandbox"]
        )
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def dispatch(route):
            request = route.request
            path = urlsplit(request.url).path
            response = client.request(
                request.method,
                path,
                content=request.post_data_buffer,
                headers={"content-type": request.headers.get("content-type", "")},
            )
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={"content-type": response.headers.get("content-type", "text/plain")},
            )

        page.route("**/*", dispatch)
        try:
            yield page
            assert errors == [], f"Uncaught browser errors: {errors}"
        finally:
            browser.close()


def add_account(client, name, balance="0.00"):
    response = client.post("/serenity-api/accounts", json={
        "name": name, "account_type": "Checking",
        "classification": "Personal", "opening_balance": balance,
    })
    assert response.status_code == 201
    return response.json()


def add_transaction(client, account_id, *, amount="5.00", description="Initial"):
    response = client.post(f"/serenity-api/accounts/{account_id}/transactions", json={
        "date": "2026-09-21", "transaction_type": "Expense",
        "amount": amount, "description": description, "category": "Food",
        "merchant": "Corner Store",
    })
    assert response.status_code == 201
    return response.json()


def account_balance(client, account_id):
    return client.get(f"/serenity-api/accounts/{account_id}").json()["current_balance"]


def today_in_browser(page):
    return page.evaluate("""() => {
      const d = new Date();
      return [d.getFullYear(), String(d.getMonth() + 1).padStart(2, "0"),
              String(d.getDate()).padStart(2, "0")].join("-");
    }""")


def test_edit_prefill_cancel_save_and_switch_accounts(page, client):
    first = add_account(client, "Checking", "20.00")
    second = add_account(client, "Savings", "80.00")
    add_transaction(client, first["id"], amount="4.25", description="Old purchase")
    page.goto("http://serenity.test/accounts")
    account_select = page.locator("#transaction-form select[name=account_id]")
    account_select.select_option(str(first["id"]))
    row = page.locator("#transactions-body tr").filter(has_text="Old purchase")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Edit").click()
    form = page.locator("#transaction-form")
    expect(form.locator("[name=date]")).to_have_value("2026-09-21")
    expect(form.locator("[name=transaction_type]")).to_have_value("Expense")
    expect(form.locator("[name=amount]")).to_have_value("4.25")
    expect(form.locator("[name=description]")).to_have_value("Old purchase")
    expect(form.locator("[name=category]")).to_have_value("Food")
    expect(form.locator("[name=merchant]")).to_have_value("Corner Store")
    expect(form.locator("[name=classification]")).to_have_value("Personal")
    expect(form.get_by_role("button", name="Save changes")).to_be_visible()

    form.get_by_role("button", name="Cancel edit").click()
    expect(form.get_by_role("button", name="Record transaction")).to_be_visible()
    expect(form.locator("[name=amount]")).to_have_value("")
    expect(form.locator("[name=date]")).to_have_value(today_in_browser(page))
    expect(row).to_be_visible()
    assert account_balance(client, first["id"]) == "15.75"

    row.get_by_role("button", name="Edit").click()
    form.locator("[name=date]").fill("2026-09-22")
    form.locator("[name=transaction_type]").select_option("Income")
    form.locator("[name=amount]").fill("10.30")
    form.locator("[name=description]").fill("Refund")
    form.locator("[name=category]").fill("Returns")
    form.get_by_role("button", name="Save changes").click()
    expect(page.locator("#transaction-message")).to_have_text("Transaction updated.")
    expect(page.locator("#transactions-body")).to_contain_text("Refund")
    expect(page.locator("#corrections-body")).to_contain_text("Old purchase")
    expect(page.locator("#corrections-body")).to_contain_text("Refund")
    expect(form.locator("[name=date]")).to_have_value(today_in_browser(page))
    expect(form.locator("[name=amount]")).to_have_value("")
    expect(form.get_by_role("button", name="Record transaction")).to_be_visible()
    assert account_balance(client, first["id"]) == "30.30"
    assert client.get("/serenity-api/dashboard/summary").json()["total_balance"] == "110.30"

    page.locator("#transactions-body").get_by_role("button", name="Edit").click()
    account_select.select_option(str(second["id"]))
    expect(form.get_by_role("button", name="Record transaction")).to_be_visible()
    expect(form.locator("[name=description]")).to_have_value("")
    expect(form.locator("[name=date]")).to_have_value(today_in_browser(page))
    expect(page.locator("#corrections-body")).to_contain_text("No corrections yet")
    assert account_balance(client, first["id"]) == "30.30"


def test_delete_confirmation_and_cancel(page, client):
    account = add_account(client, "Checking", "50.00")
    transaction = add_transaction(client, account["id"], description="Duplicate")
    page.goto("http://serenity.test/accounts")
    row = page.locator("#transactions-body tr").filter(has_text="Duplicate")
    expect(row).to_be_visible()
    page.once("dialog", lambda dialog: dialog.dismiss())
    row.get_by_role("button", name="Delete").click()
    expect(row).to_be_visible()
    assert account_balance(client, account["id"]) == "45.00"

    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Delete").click()
    expect(page.locator("#transaction-message")).to_have_text("Transaction deleted.")
    expect(page.locator("#transactions-body")).to_contain_text("No transactions yet")
    expect(page.locator("#corrections-body")).to_contain_text("Deleted")
    expect(page.locator("#corrections-body")).to_contain_text("Duplicate")
    assert account_balance(client, account["id"]) == "50.00"
    assert client.delete(
        f"/serenity-api/accounts/{account['id']}/transactions/{transaction['id']}"
    ).status_code == 404


def test_failed_save_keeps_edit_form_recoverable(page, client):
    account = add_account(client, "Checking")
    transaction = add_transaction(client, account["id"])
    page.goto("http://serenity.test/accounts")
    page.locator("#transactions-body").get_by_role("button", name="Edit").click()
    form = page.locator("#transaction-form")
    form.locator("[name=amount]").fill("6.75")

    def fail_once(route):
        if route.request.method == "PUT":
            route.fulfill(
                status=503, content_type="application/json",
                body='{"detail":"Please retry"}',
            )
        else:
            route.fallback()

    page.route(f"**/transactions/{transaction['id']}", fail_once, times=1)
    form.get_by_role("button", name="Save changes").click()
    expect(page.locator("#transaction-message")).to_have_text("Please retry")
    expect(page.locator("#transaction-message")).to_have_class("message error")
    expect(form.get_by_role("button", name="Save changes")).to_be_visible()
    expect(form.locator("[name=amount]")).to_have_value("6.75")
    assert account_balance(client, account["id"]) == "-5.00"

    form.get_by_role("button", name="Save changes").click()
    expect(page.locator("#transaction-message")).to_have_text("Transaction updated.")
    expect(form.get_by_role("button", name="Record transaction")).to_be_visible()
    assert account_balance(client, account["id"]) == "-6.75"


def test_failed_delete_leaves_transaction_available_for_retry(page, client):
    account = add_account(client, "Checking")
    transaction = add_transaction(client, account["id"])
    page.goto("http://serenity.test/accounts")
    row = page.locator("#transactions-body tr").filter(has_text="Initial")
    expect(row).to_be_visible()

    def fail_once(route):
        if route.request.method == "DELETE":
            route.fulfill(
                status=503, content_type="application/json",
                body='{"detail":"Delete failed, retry"}',
            )
        else:
            route.fallback()

    page.route(f"**/transactions/{transaction['id']}", fail_once, times=1)
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Delete").click()
    expect(page.locator("#transaction-message")).to_have_text("Delete failed, retry")
    expect(row).to_be_visible()
    assert account_balance(client, account["id"]) == "-5.00"

    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Delete").click()
    expect(page.locator("#transactions-body")).to_contain_text("No transactions yet")
    assert account_balance(client, account["id"]) == "0.00"


def test_new_transaction_can_use_business_classification(page, client):
    account = add_account(client, "Checking", "100.00")
    page.goto("http://serenity.test/accounts")
    form = page.locator("#transaction-form")
    form.locator("[name=account_id]").select_option(str(account["id"]))
    expect(form.locator("[name=transaction_type]")).to_have_value("Expense")
    form.locator("[name=amount]").fill("89.99")
    form.locator("[name=description]").fill("Replacement SSD")
    form.locator("[name=classification]").select_option("Business")
    form.locator("[name=merchant]").fill("Newegg")
    form.get_by_role("button", name="Record transaction").click()
    expect(page.locator("#transaction-message")).to_have_text("Transaction recorded.")
    row = page.locator("#transactions-body tr").filter(has_text="Replacement SSD")
    expect(row).to_contain_text("Business")
    expect(row).to_contain_text("Newegg")
    assert account_balance(client, account["id"]) == "10.01"