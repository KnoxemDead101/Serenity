"""Chromium console checks use synthetic authorized fixtures, not live sign-in."""

import json

import pytest
from playwright.sync_api import expect
from sqlalchemy import text

from services import system_health

URL = "http://serenity.test/system"
PATH = "/serenity-api/system/health"


def test_normal_console_and_navigation(page):
    page.goto("http://serenity.test/goals")
    page.get_by_role("link", name="System", exact=True).click()
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")
    expect(page.locator("#system-writes")).to_have_text("Enabled")
    expect(page.locator("#system-checks li")).to_have_count(6)
    expect(page.locator('[data-key="backups"]')).to_contain_text("UNVERIFIED")
    expect(page.locator('[data-key="market_data"]')).to_contain_text("MANUAL")
    expect(page.locator("#system-migration-observed")).to_have_text("Not observed (unknown)")
    expect(page.locator("#system-version")).to_have_text("0.2.0")


def test_actual_read_only_backend_visible_without_operational_controls(page, monkeypatch):
    monkeypatch.setattr(system_health, "write_state", lambda connection: "READ_ONLY")
    page.goto(URL)
    expect(page.locator("#system-status")).to_have_attribute("data-state", "READ_ONLY")
    expect(page.locator("#system-writes")).to_have_text("Paused")
    expect(page.locator('[data-key="schema"]')).to_contain_text("AVAILABLE")
    assert page.locator("main form").count() == 0


def test_actual_missing_schema_is_unavailable_not_no_records(page, db):
    db.execute(text("DROP TABLE goals"))
    db.commit()
    page.goto(URL)
    expect(page.locator("#system-status")).to_have_attribute("data-state", "UNAVAILABLE")
    expect(page.locator("#system-message")).to_contain_text("Unknown does not mean empty")
    expect(page.locator('[data-key="schema"]')).to_contain_text("UNAVAILABLE")
    expect(page.locator('#data-health-readings > li[data-domain="accounts"]')).to_contain_text("Count: Unknown")


@pytest.mark.parametrize("failure", ["network", "invalid_json", "malformed", "inconsistent"])
def test_failed_refresh_removes_all_previous_success_evidence(page, client, failure):
    page.goto(URL)
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")
    if failure == "network":
        page.route("**" + PATH, lambda route: route.abort())
    else:
        data = client.get(PATH).json()
        data["writes_enabled"] = False
        body = {
            "invalid_json": "private-diagnostic-not-json",
            "malformed": '{"state":"NORMAL"}',
            "inconsistent": json.dumps(data),
        }[failure]
        page.route("**" + PATH, lambda route: route.fulfill(
            status=200, content_type="application/json", body=body,
        ))
    page.locator("#system-refresh").click()
    expect(page.locator("#system-status")).to_have_attribute("data-state", "UNAVAILABLE")
    expect(page.locator("#system-meta")).to_be_hidden()
    expect(page.locator("#system-checks-panel")).to_be_hidden()
    expect(page.locator("#system-version")).to_have_text("")
    expect(page.locator("#system-message")).to_contain_text("unknown")
    assert "private-diagnostic" not in page.locator("main").inner_text()
    page.unroute("**" + PATH)
    page.locator("#system-refresh").click()
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")


@pytest.mark.parametrize("inactive", [False, True])
def test_auth_failure_clears_console_evidence(page, inactive):
    page.goto(URL)
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")
    headers = {"X-Serenity-Account-Status": "inactive"} if inactive else {}
    page.route("**" + PATH, lambda route: route.fulfill(
        status=403 if inactive else 401, headers=headers,
        content_type="application/json", body='{"detail":"No session"}',
    ))
    page.locator("#system-refresh").click()
    expect(page.locator(".session-recovery")).to_be_visible()
    assert page.locator("#system-status").count() == 0
    assert page.locator("#system-checks").count() == 0
    assert page.locator("#data-health-readings").count() == 0


def test_cross_tab_signout_during_request_cannot_restore_evidence(page):
    page.goto(URL)
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")
    page.evaluate("showSessionRecovery()")
    expect(page.locator(".session-recovery")).to_be_visible()
    assert page.locator("#system-status").count() == 0


def test_mobile_console_is_readable_and_menu_works(page):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(URL)
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")
    page.get_by_role("button", name="Menu", exact=True).click()
    expect(page.get_by_role("link", name="Goals", exact=True)).to_be_visible()
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")