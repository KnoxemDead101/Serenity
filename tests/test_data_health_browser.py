"""Plain HTML Chromium evidence flows against disposable authorized records."""

import json
from datetime import timedelta

import pytest
from playwright.sync_api import expect

from services import finance_service
from tests.test_data_health import NOW, PATH, seed_inputs

URL = "http://serenity.test/system"


def domain(page, key):
    return page.locator(f'#data-health-readings > li[data-domain="{key}"]')


def test_empty_readings_show_missing_not_verified_zero_and_working_source_links(page):
    page.goto(URL)
    expect(page.locator("#data-health-panel")).to_be_visible()
    expect(page.locator("#data-health-readings > li")).to_have_count(5)
    expect(domain(page, "accounts")).to_contain_text("0 recorded (not a confirmed real-world zero)")
    expect(domain(page, "income")).to_contain_text("Basis: planned")
    expect(domain(page, "accounts")).to_have_attribute("data-status", "MISSING")
    domain(page, "accounts").get_by_role("link").click()
    expect(page).to_have_url("http://serenity.test/accounts")
    expect(page.get_by_role("heading", name="Accounts", exact=True)).to_be_visible()


def test_partial_manual_data_is_explained_without_private_names_or_amounts(page, db):
    seed_inputs(db)
    page.goto(URL)
    expect(domain(page, "accounts")).to_have_attribute("data-status", "PARTIAL")
    expect(domain(page, "accounts")).to_contain_text("missing transaction history")
    expect(domain(page, "income")).to_contain_text("not received money")
    expect(domain(page, "income")).to_contain_text("take-home is unknown", ignore_case=True)
    expect(domain(page, "debts")).to_have_attribute("data-status", "PARTIAL")
    assert "Private" not in page.locator("#data-health-panel").inner_text()
    assert page.locator("#data-health-panel form").count() == 0
    domain(page, "income").get_by_role("link").click()
    expect(page).to_have_url("http://serenity.test/income")


def test_malformed_dataset_has_unknown_count_not_zero_and_preserves_runtime_state(page, db):
    rows = seed_inputs(db)
    rows[2].balance_cents = -1
    db.commit()
    page.goto(URL)
    expect(domain(page, "debts")).to_have_attribute("data-status", "INCONSISTENT")
    expect(domain(page, "debts")).to_contain_text("Count: Unknown")
    expect(domain(page, "debts")).to_contain_text("not zero")
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")


def test_unavailable_dataset_never_shows_synthetic_zero(page, db, monkeypatch):
    seed_inputs(db)
    monkeypatch.setattr(finance_service, "list_debts",
                        lambda *args: (_ for _ in ()).throw(RuntimeError("Private error")))
    page.goto(URL)
    expect(domain(page, "debts")).to_have_attribute("data-status", "UNAVAILABLE")
    expect(domain(page, "debts")).to_contain_text("Count: Unknown")
    expect(domain(page, "debts")).to_contain_text("Unknown does not mean empty")
    expect(domain(page, "investments")).to_have_attribute("data-status", "PARTIAL")
    assert "Private error" not in page.locator("main").inner_text()


def test_stale_manual_snapshot_is_review_reminder_not_price_verification(page, db):
    rows = seed_inputs(db)
    rows[2].updated_at = NOW - timedelta(days=31)
    db.commit()
    page.goto(URL)
    expect(domain(page, "debts")).to_have_attribute("data-status", "STALE")
    expect(domain(page, "debts")).to_contain_text("30 or more days")
    expect(domain(page, "debts")).to_contain_text("not proof its amount is wrong")


@pytest.mark.parametrize("damage", [
    "missing", "negative", "duplicate", "unknown_zero", "source", "findings",
    "wrong_basis", "wrong_source", "contradictory_finding",
])
def test_malformed_data_health_refresh_clears_previous_evidence(page, client, damage):
    page.goto(URL)
    expect(page.locator("#data-health-panel")).to_be_visible()
    data = client.get(PATH).json()
    h = data["data_health"]
    r = h["readings"][0]
    if damage == "missing":
        del data["data_health"]
    elif damage == "negative":
        r["record_count"] = -1
    elif damage == "duplicate":
        h["readings"][1] = r
    elif damage == "unknown_zero":
        r["status"] = "UNAVAILABLE"
    elif damage == "source":
        r["source"] = "javascript:alert(1)"
    elif damage == "wrong_basis":
        r["basis"] = "PLANNED"
    elif damage == "wrong_source":
        r["source"] = "/income"
    elif damage == "contradictory_finding":
        r["findings"][0]["status"] = "MANUAL"
    else:
        r["findings"] = []
    page.route("**" + PATH, lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(data),
    ))
    page.locator("#system-refresh").click()
    expect(page.locator("#system-status")).to_have_attribute("data-state", "UNAVAILABLE")
    expect(page.locator("#data-health-panel")).to_be_hidden()
    expect(page.locator("#data-health-readings > li")).to_have_count(0)
    expect(page.locator("#data-health-checked")).to_have_text("")


def test_data_health_text_is_not_html_and_phone_layout_does_not_overflow(page, client):
    data = client.get(PATH).json()
    data["data_health"]["readings"][0]["findings"][0]["message"] = '<img src=x onerror="alert(1)">'
    page.route("**" + PATH, lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(data),
    ))
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(URL)
    expect(domain(page, "accounts")).to_contain_text("<img src=x")
    assert page.locator("#data-health-panel img").count() == 0
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")