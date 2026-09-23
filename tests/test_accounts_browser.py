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
        context = browser.new_context()
        page = context.new_page()
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

        page.context.route("**/*", dispatch)
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


def test_edit_and_deactivate_account(page, client):
    account = add_account(client, "Checking", "20.00")
    page.goto("http://serenity.test/accounts")
    row = page.locator("#accounts-body tr").filter(has_text="Checking")
    expect(row).to_be_visible()
    row.get_by_role("button", name="Edit").click()
    account_form = page.locator("#account-form")
    account_form.locator("[name=name]").fill("Everyday Checking")
    account_form.get_by_role("button", name="Save account").click()
    expect(page.locator("#form-message")).to_have_text('Saved "Everyday Checking".')
    page.once("dialog", lambda dialog: dialog.accept())
    page.locator("#accounts-body tr").filter(has_text="Everyday Checking").get_by_role(
        "button", name="Deactivate"
    ).click()
    expect(page.locator("#accounts-body tr.inactive")).to_contain_text("Inactive")
    expect(page.locator("#transaction-form select[name=account_id] option")).to_have_count(1)
    expect(page.locator("#transaction-form button[type=submit]")).to_be_disabled()
    assert client.get(f"/serenity-api/accounts/{account['id']}").json()["active"] is False


def test_inactive_account_history_remains_readable_and_editable(page, client):
    account = add_account(client, "Archived Checking")
    transaction = add_transaction(client, account["id"], description="Before deactivation")
    client.put(
        f"/serenity-api/accounts/{account['id']}/transactions/{transaction['id']}",
        json={
            "date": "2026-09-21",
            "transaction_type": "Expense",
            "amount": "6.00",
            "description": "After deactivation",
        },
    )
    assert client.post(f"/serenity-api/accounts/{account['id']}/deactivate").status_code == 200

    page.goto("http://serenity.test/accounts")
    account_select = page.locator("#transaction-form select[name=account_id]")
    account_select.select_option(str(account["id"]))
    expect(page.locator("#transactions-body")).to_contain_text("After deactivation")
    expect(page.locator("#corrections-body")).to_contain_text("Before deactivation")
    expect(page.locator("#transaction-form button[type=submit]")).to_be_disabled()

    page.locator("#transactions-body").get_by_role("button", name="Edit").click()
    expect(page.locator("#transaction-form button[type=submit]")).to_be_enabled()
    expect(page.locator("#transaction-form [name=description]")).to_have_value("After deactivation")


def test_accounts_and_transactions_table_columns_align(page, client):
    account = add_account(client, "Column Check")
    add_transaction(client, account["id"], description="Column transaction")
    page.goto("http://serenity.test/accounts")
    account_select = page.locator("#transaction-form select[name=account_id]")
    account_select.select_option(str(account["id"]))
    expect(page.locator("#accounts-body tr").first.locator("td")).to_have_count(6)
    expect(page.locator("#transactions-body tr").first.locator("td")).to_have_count(9)
    accounts_headers = page.locator("#accounts-body").locator("xpath=ancestor::table[1]").locator("th")
    transaction_headers = page.locator("#transactions-body").locator("xpath=ancestor::table[1]").locator("th")
    expect(accounts_headers).to_have_count(6)
    expect(transaction_headers).to_have_count(9)
    expect(transaction_headers.nth(5)).to_have_text("For")


def test_accounts_page_fits_a_phone_screen(page, client):
    add_account(client, "Checking", "20.00")
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto("http://serenity.test/accounts")
    expect(page.locator("#accounts-body tr").first).to_contain_text("Checking")
    overflow = page.evaluate(
        "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
    )
    assert overflow <= 1


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


def test_setup_page_manages_business_and_dependent_surfaces(page, client):
    page.goto("http://serenity.test/setup")
    expect(page.get_by_role("heading", name="Setup")).to_be_visible()
    expect(page.get_by_role("heading", name="Businesses")).to_be_visible()
    expect(page.get_by_role("heading", name="Dependents")).to_be_visible()
    expect(page.locator("#business-form [name=name]")).to_be_visible()
    expect(page.locator("#dependent-form [name=display_name]")).to_be_visible()


def test_revocation_clears_open_financial_page_and_outage_does_not_loop(page, client):
    add_account(client, "Private emergency fund", "4321.00")
    page.goto("http://serenity.test/accounts")
    expect(page.locator("#accounts-body")).to_contain_text("Private emergency fund")
    page.locator("#account-form [name=notes]").fill("Unsubmitted sensitive note")
    page.route("**/serenity-api/accounts", lambda route: route.fulfill(
        status=401, content_type="application/json", body='{"detail":"Sign in required"}'
    ))
    # A protected request from an already-open page, not a page load.
    page.evaluate("apiGet('/serenity-api/accounts').catch(() => {})")
    recovery = page.get_by_role("alert")
    expect(recovery).to_contain_text("Your session has ended")
    assert "Private emergency fund" not in page.locator("main").inner_text()
    assert "Unsubmitted sensitive note" not in page.locator("main").inner_text()
    expect(page.locator("#account-form")).to_have_count(0)
    sign_in = recovery.get_by_role("link", name="Sign in again")
    assert sign_in.get_attribute("href") == "/sign-in?next=%2Faccounts"
    assert page.url == "http://serenity.test/accounts"

    checks = []
    def backend_unavailable(route):
        checks.append(route.request.url)
        route.fulfill(status=503, content_type="application/json",
                      body='{"detail":"Temporarily unavailable"}')

    page.route("**/serenity-api/auth/me", backend_unavailable)
    recovery.get_by_role("button", name="Retry session").click()
    expect(recovery.get_by_role("status")).to_contain_text("still unavailable")
    assert len(checks) == 1
    assert page.url == "http://serenity.test/accounts"
    page.wait_for_timeout(300)
    assert len(checks) == 1  # no automatic retries or redirects
    assert "Private emergency fund" not in page.locator("main").inner_text()


def test_safe_return_path_rejects_external_destinations(page, client):
    page.goto("http://serenity.test/accounts")
    assert page.evaluate("safeReturnPath('//attacker.test/steal')") == "/"
    assert page.evaluate("safeReturnPath('/\\\\attacker.test')") == "/"
    assert page.evaluate("safeReturnPath('https://attacker.test/')") == "/"
    assert page.evaluate("safeReturnPath('/accounts?filter=checking')") == "/accounts?filter=checking"
    page.add_script_tag(url="http://serenity.test/static/js/auth.js")
    assert page.evaluate("safeSignInReturnPath('//attacker.test')") == "/"
    assert page.evaluate("safeSignInReturnPath('/\\\\attacker.test')") == "/"
    assert page.evaluate("safeSignInReturnPath('/accounts?filter=checking')") == "/accounts?filter=checking"


def test_sign_out_clears_an_idle_second_tab_even_when_clerk_fails(page, client):
    add_account(client, "Cross-tab private savings", "4321.00")
    page.goto("http://serenity.test/accounts")
    other = page.context.new_page()
    other.goto("http://serenity.test/accounts")
    expect(other.locator("#accounts-body")).to_contain_text("Cross-tab private savings")
    other.locator("#account-form [name=notes]").fill("Private unsaved draft")
    other.evaluate("""() => {
        window.signOutMessages = [];
        window.observer = new BroadcastChannel("serenity-session");
        observer.onmessage = event => signOutMessages.push(event.data);
    }""")
    # Exercise the real sign-out page, but simulate the Clerk CDN being down.
    deletes = []
    page.route("**/serenity-api/auth/session", lambda route: (
        deletes.append(route.request.method),
        route.fulfill(status=204, body="")
    ))
    page.context.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
    page.goto("http://serenity.test/sign-out")
    expect(other.get_by_role("alert")).to_contain_text("Your session has ended")
    expect(page).to_have_url("http://serenity.test/sign-in")
    assert deletes == ["DELETE"]
    assert other.evaluate("signOutMessages") == ["signed-out"]
    assert "Cross-tab private savings" not in other.locator("main").inner_text()
    assert "4,321.00" not in other.locator("main").inner_text()
    expect(other.locator("#account-form")).to_have_count(0)
    assert other.url == "http://serenity.test/accounts"
    assert other.evaluate("Object.keys(localStorage)") == []
    assert other.evaluate("Object.keys(sessionStorage)") == []
    # A late successful response must not restore data after the notification.
    assert other.evaluate("""async () => {
        try {
            await handleResponse(new Response('{"name":"private"}', {status:200}));
            return false;
        } catch { return true; }
    }""")
    other.close()


def test_tab_revisit_detects_revocation_without_broadcast_channel(page, client):
    add_account(client, "Revoked-session savings", "123.00")
    page.goto("http://serenity.test/accounts")
    other = page.context.new_page()
    other.add_init_script("window.BroadcastChannel = undefined")
    other.goto("http://serenity.test/accounts")
    expect(other.locator("#accounts-body")).to_contain_text("Revoked-session savings")
    other.locator("#account-form [name=notes]").fill("Draft to discard")
    checks = []

    def revoked(route):
        checks.append(route.request.url)
        route.fulfill(status=401, content_type="application/json", body="{}")

    other.route("**/serenity-api/auth/me", revoked)
    # Headless Chromium does not reliably hide pages on bring_to_front.
    # Drive the browser visibility event explicitly to model leaving/returning.
    other.evaluate("""() => {
        Object.defineProperty(document, "visibilityState", {
            configurable: true, value: "hidden"
        });
        document.dispatchEvent(new Event("visibilitychange"));
    }""")
    page.bring_to_front()
    assert checks == []
    other.evaluate("""() => {
        Object.defineProperty(document, "visibilityState", {
            configurable: true, value: "visible"
        });
        document.dispatchEvent(new Event("visibilitychange"));
        window.dispatchEvent(new Event("focus"));
    }""")
    expect(other.get_by_role("alert")).to_contain_text("Your session has ended")
    expect(other.locator("#account-form")).to_have_count(0)
    assert "Revoked-session savings" not in other.locator("main").inner_text()
    assert checks == ["http://serenity.test/serenity-api/auth/me"]
    other.evaluate("window.dispatchEvent(new Event('focus'))")
    other.wait_for_timeout(400)
    assert len(checks) == 1
    assert other.url == "http://serenity.test/accounts"
    other.close()


def test_focus_session_checks_are_bounded_and_outage_never_redirects(page, client):
    page.clock.install()
    page.goto("http://serenity.test/accounts")
    checks = []

    def unavailable(route):
        checks.append(route.request.url)
        route.fulfill(status=503, content_type="application/json", body="{}")

    page.route("**/serenity-api/auth/me", unavailable)
    page.evaluate("""() => {
        for (let i = 0; i < 20; i++) {
            window.dispatchEvent(new Event("focus"));
            document.dispatchEvent(new Event("visibilitychange"));
        }
    }""")
    page.clock.run_for(300)
    page.wait_for_function("sessionCheckInFlight === false")
    assert len(checks) == 1
    page.evaluate("window.dispatchEvent(new Event('focus'))")
    page.clock.run_for(14000)
    assert len(checks) == 1
    page.clock.run_for(1100)
    page.wait_for_function("sessionCheckInFlight === false")
    assert len(checks) == 2
    page.clock.run_for(60000)
    assert len(checks) == 2  # no polling or automatic outage retries
    assert page.url == "http://serenity.test/accounts"
    expect(page.get_by_role("alert")).to_have_count(0)


def test_manual_retry_only_reopens_page_after_server_confirms_session(page, client):
    add_account(client, "Private savings", "52.00")
    page.goto("http://serenity.test/accounts")
    expect(page.locator("#accounts-body")).to_contain_text("Private savings")
    page.route("**/serenity-api/accounts", lambda route: route.fulfill(
        status=401, content_type="application/json", body='{"detail":"Sign in required"}'
    ), times=1)
    page.evaluate("apiGet('/serenity-api/accounts').catch(() => {})")
    expect(page.get_by_role("alert")).to_be_visible()
    page.route("**/serenity-api/auth/me", lambda route: route.fulfill(
        status=200, content_type="application/json", body='{"user_id":"test-owner"}'
    ))
    page.get_by_role("button", name="Retry session").click()
    expect(page.locator("#accounts-body")).to_contain_text("Private savings")
    expect(page.get_by_role("alert")).to_have_count(0)