"""Exercise finance edits and permanent deletion in the real Finances page."""

import shutil
from urllib.parse import urlsplit

import pytest
from playwright.sync_api import expect, sync_playwright


@pytest.fixture
def page(client):
    executable = shutil.which("chromium")
    if executable is None:
        pytest.fail("Chromium is required for Finances browser tests")

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


def test_finance_edits_preserve_notes(page, client):
    bill = client.post(
        "/serenity-api/bills",
        json={
            "name": "Rent",
            "amount": "1200.00",
            "due_date": "2026-10-01",
            "frequency": "Monthly",
            "notes": "Pay from checking",
        },
    ).json()
    debt = client.post(
        "/serenity-api/debts",
        json={
            "name": "Card",
            "debt_type": "Credit Card",
            "balance": "100.00",
            "notes": "Keep utilization low",
        },
    ).json()
    investment = client.post(
        "/serenity-api/investments",
        json={
            "name": "Index fund",
            "quantity": "1",
            "cost_basis": "10.00",
            "current_value": "11.00",
            "notes": "Long-term holding",
        },
    ).json()

    page.goto("http://serenity.test/finances")
    sections = (
        ("bills", bill, "Rent", "Updated rent", "Pay from checking"),
        ("debts", debt, "Card", "Updated card", "Keep utilization low"),
        ("investments", investment, "Index fund", "Updated fund", "Long-term holding"),
    )
    for path, record, old_name, new_name, note in sections:
        row = page.locator(f"#{path}-body tr").filter(has_text=old_name)
        expect(row).to_be_visible()
        row.get_by_role("button", name="Edit").click()
        form = page.locator(f"#{path[:-1]}-form")
        expect(form.locator("[name=notes]")).to_have_value(note)
        form.locator("[name=name]").fill(new_name)
        form.get_by_role("button", name=f"Save {path[:-1]}").click()
        expect(page.locator(f"#{path[:-1]}-message")).to_have_text(
            f"{path[:-1].capitalize()} saved."
        )
        assert client.get(f"/serenity-api/{path}/{record['id']}").json()["notes"] == note


FINANCE_CASES = (
    ("bills", {"name": "Rent", "amount": "1200.00", "due_date": "2026-10-01",
               "frequency": "Monthly"}, "bill_count", "monthly_bill_total", "1200.00"),
    ("debts", {"name": "Card", "debt_type": "Credit Card", "balance": "500.00",
               "interest_rate": "6.875", "minimum_payment": "25.00"},
     "debt_count", "debt_balance", "500.00"),
    ("investments", {"name": "Index fund", "quantity": "2.5",
                     "cost_basis": "400.00", "current_value": "450.00"},
     "investment_count", "investment_value", "450.00"),
)


@pytest.mark.parametrize("path,body,count_field,total_field,total", FINANCE_CASES)
@pytest.mark.parametrize("inactive", (False, True))
def test_finance_delete_confirm_cancel_and_edit_reset(
    page, client, path, body, count_field, total_field, total, inactive
):
    created = client.post(f"/serenity-api/{path}", json=body)
    assert created.status_code == 201, created.text
    record = created.json()
    url = f"/serenity-api/{path}/{record['id']}"
    if inactive:
        assert client.post(f"{url}/deactivate").status_code == 200
    initial = client.get("/serenity-api/dashboard/summary").json()
    assert initial[count_field] == (0 if inactive else 1)
    assert initial[total_field] == ("0.00" if inactive else total)
    delete_requests = []
    page.on("request", lambda request: delete_requests.append(request.url)
            if request.method == "DELETE" and url in request.url else None)
    page.goto("http://serenity.test/finances")
    row = page.locator(f"#{path}-body tr").filter(has_text=body["name"])
    expect(row).to_be_visible()
    if inactive:
        expect(row.get_by_text("Inactive")).to_be_visible()
    expect(row.get_by_role("button", name="Reactivate")).to_have_count(0)
    expect(row.get_by_role("button", name="Deactivate")).to_have_count(0)
    row.get_by_role("button", name="Edit").click()
    form = page.locator(f"#{path[:-1]}-form")
    form.locator("[name=name]").fill("Unsaved changes")
    prompts = []
    def dismiss(dialog):
        prompts.append(dialog.message)
        dialog.dismiss()
    page.once("dialog", dismiss)
    row.get_by_role("button", name="Delete").click()
    assert "permanently" in prompts[0]
    assert "cannot be undone" in prompts[0]
    assert "history will not be restored" in prompts[0]
    expect(row).to_be_visible()
    expect(form.locator("[name=name]")).to_have_value("Unsaved changes")
    assert not delete_requests
    assert client.get(url).status_code == 200
    assert client.get("/serenity-api/dashboard/summary").json() == initial

    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Delete").click()
    expect(page.locator(f"#{path}-body")).to_contain_text("No records yet.")
    expect(page.locator(f"#{path[:-1]}-message")).to_have_text(
        f"{path[:-1].capitalize()} deleted."
    )
    expect(form.locator("[name=name]")).to_have_value("")
    expect(form.get_by_role("button", name=f"Add {path[:-1]}")).to_be_visible()
    assert len(delete_requests) == 1
    assert client.get(url).status_code == 404
    updated = client.get("/serenity-api/dashboard/summary").json()
    assert updated[count_field] == 0
    assert updated[total_field] == "0.00"


@pytest.mark.parametrize("path,body,count_field,total_field,total", FINANCE_CASES)
def test_finance_delete_failure_retains_row_and_edit(page, client, path, body,
                                                      count_field, total_field, total):
    created = client.post(f"/serenity-api/{path}", json=body)
    assert created.status_code == 201, created.text
    record = created.json()
    url = f"/serenity-api/{path}/{record['id']}"
    page.goto("http://serenity.test/finances")
    row = page.locator(f"#{path}-body tr").filter(has_text=body["name"])
    expect(row).to_be_visible()
    row.get_by_role("button", name="Edit").click()
    form = page.locator(f"#{path[:-1]}-form")
    form.locator("[name=name]").fill("Draft kept")
    page.route(f"**{url}", lambda route: route.fulfill(
        status=503, content_type="application/json",
        body='{"detail":"Deletion unavailable; please retry"}'
    ) if route.request.method == "DELETE" else route.continue_())
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Delete").click()
    expect(page.locator(f"#{path[:-1]}-message")).to_have_text(
        "Deletion unavailable; please retry"
    )
    expect(row).to_be_visible()
    expect(form.locator("[name=name]")).to_have_value("Draft kept")
    expect(form.get_by_role("button", name=f"Save {path[:-1]}")).to_be_visible()
    assert client.get(url).status_code == 200
    summary = client.get("/serenity-api/dashboard/summary").json()
    assert summary[count_field] == 1
    assert summary[total_field] == total