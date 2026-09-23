"""Exercise finance note preservation in the real Finances page."""

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