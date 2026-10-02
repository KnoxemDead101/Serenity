"""Actual plain-HTML owner review controls backed by disposable records."""

import json

import pytest
from playwright.sync_api import expect

from models.verification import Verification
from sqlalchemy import select
from tests.test_data_health import seed_inputs
from tests.test_verification import PATH, payload, save, targets

URL = "http://serenity.test/system"


def debt_item(page):
    return page.locator('#verification-targets > li[data-kind="debt_balance"]')


def fill(page, item, date="2026-10-02", evidence="Synthetic lender statement"):
    item.locator('input[type="date"]').fill(date)
    item.locator("textarea").fill(evidence)
    item.locator('input[type="checkbox"]').check()


def test_create_replace_delete_and_summary_keeps_private_evidence_out(page, db):
    seed_inputs(db)
    page.goto(URL)
    item = debt_item(page)
    expect(item).to_have_attribute("data-status", "UNKNOWN")
    expect(item.locator('input[type="date"]')).to_have_value("")
    expect(item).to_contain_text("Unknown - never verified")
    fill(page, item)
    item.get_by_role("button", name="Save evidence", exact=True).click()
    expect(item).to_have_attribute("data-status", "VERIFIED")
    expect(item).to_contain_text("Synthetic lender statement")
    expect(item).to_contain_text("2026-10-02")
    expect(page.locator('#data-health-readings > li[data-domain="debts"]')).to_have_attribute("data-status", "MANUAL")
    assert "Synthetic lender statement" not in page.locator("#data-health-panel").inner_text()
    fill(page, item, evidence="<img src=x onerror=alert(1)> replaced evidence")
    item.get_by_role("button", name="Replace evidence").click()
    expect(item).to_contain_text("<img src=x")
    assert page.locator("#system-verification-panel img").count() == 0
    assert len(db.scalars(select(Verification)).all()) == 1
    page.once("dialog", lambda dialog: dialog.accept())
    item.get_by_role("button", name="Delete evidence").click()
    expect(item).to_have_attribute("data-status", "UNKNOWN")
    expect(item).not_to_contain_text("replaced evidence")


def test_future_date_rejected_without_fabricated_success(page, db):
    seed_inputs(db)
    page.goto(URL)
    item = debt_item(page)
    fill(page, item, date="2999-01-01")
    item.get_by_role("button", name="Save evidence", exact=True).click()
    expect(item.locator('[role="status"]')).to_contain_text("future")
    expect(item).to_have_attribute("data-status", "UNKNOWN")
    assert db.scalar(select(Verification)) is None


def test_snapshot_changed_while_reviewing_requires_reload(page, db):
    rows = seed_inputs(db)
    page.goto(URL)
    item = debt_item(page)
    expect(item).to_contain_text("$0.00")
    rows[2].balance_cents = 100
    db.commit()
    fill(page, item)
    item.get_by_role("button", name="Save evidence", exact=True).click()
    expect(page.locator("#verification-message")).to_contain_text("check the new snapshot")
    expect(item).to_contain_text("$1.00")
    expect(item).to_have_attribute("data-status", "UNKNOWN")
    assert db.scalar(select(Verification)) is None


def test_retained_deleted_source_evidence_removable_and_phone_layout(page, client, db):
    rows = seed_inputs(db)
    t = next(t for t in targets(client) if t["kind"] == "debt_balance")
    save(client, t)
    db.delete(rows[2])
    db.commit()
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(URL)
    expect(page.locator("#verification-retained > li")).to_have_count(1)
    expect(page.locator("#verification-retained")).to_contain_text("source no longer current")
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")
    page.once("dialog", lambda dialog: dialog.accept())
    page.get_by_role("button", name="Remove retained evidence").click()
    expect(page.locator("#verification-retained > li")).to_have_count(0)


def test_failed_or_malformed_refresh_drops_verification_not_financial_health(page, db):
    seed_inputs(db)
    page.goto(URL)
    expect(debt_item(page)).to_be_visible()
    page.route("**" + PATH, lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"checked_at": "2026-10-02T12:00:00+00:00", "targets": [{}], "retained": []}),
    ))
    page.locator("#system-refresh").click()
    expect(page.locator("#verification-targets > li")).to_have_count(0)
    expect(page.locator("#verification-message")).to_contain_text("could not be loaded")
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")


def test_session_ended_clears_private_evidence(page, db):
    seed_inputs(db)
    page.goto(URL)
    expect(debt_item(page)).to_be_visible()
    page.route("**" + PATH + "/**", lambda route: route.fulfill(
        status=401, content_type="application/json", body='{"detail":"Session ended"}',
    ))
    fill(page, debt_item(page))
    debt_item(page).get_by_role("button", name="Save evidence", exact=True).click()
    expect(page.locator("#system-verification-panel")).to_have_count(0)
    assert "Synthetic lender statement" not in page.locator("main").inner_text()


@pytest.mark.parametrize("damage", ["missing_date", "future_date", "missing_evidence", "duplicate", "contradiction"])
def test_malformed_verified_response_never_displays_success(page, client, db, damage):
    seed_inputs(db)
    t = next(t for t in targets(client) if t["kind"] == "debt_balance")
    save(client, t)
    data = client.get(PATH).json()
    t = next(t for t in data["targets"] if t["kind"] == "debt_balance")
    if damage == "missing_date":
        t["verification"]["as_of"] = None
    elif damage == "future_date":
        t["verification"]["as_of"] = "2999-01-01"
    elif damage == "missing_evidence":
        t["verification"]["evidence"] = " "
    elif damage == "duplicate":
        data["targets"].append(t)
    else:
        t["verification"] = None
    page.route("**" + PATH, lambda route: route.fulfill(
        status=200, content_type="application/json", body=json.dumps(data),
    ))
    page.goto(URL)
    expect(page.locator("#verification-message")).to_contain_text("could not be loaded")
    expect(page.locator("#verification-targets > li")).to_have_count(0)