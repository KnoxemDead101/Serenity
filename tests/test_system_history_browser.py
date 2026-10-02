"""History UI is checked with synthetic authorized evidence, never auth bypass."""

import json

import pytest
from playwright.sync_api import expect
from sqlalchemy import text

from services import system_health
from test_system_history import workspace

URL = "http://serenity.test/system"
HISTORY = "/serenity-api/system/history"


def test_history_baseline_repeated_refresh_transition_and_phone(page, db, monkeypatch):
    workspace(db)
    page.goto(URL)
    expect(page.locator("#system-history > li")).to_have_count(1)
    expect(page.locator("#system-history")).to_contain_text("Baseline")
    page.locator("#system-refresh").click()
    expect(page.locator("#system-refresh")).to_be_enabled()
    expect(page.locator("#system-history > li")).to_have_count(1)
    monkeypatch.setattr(system_health, "write_state", lambda connection: "READ_ONLY")
    page.locator("#system-refresh").click()
    expect(page.locator("#system-history > li")).to_have_count(2)
    expect(page.locator("#system-history > li").first).to_contain_text("READ ONLY")
    expect(page.locator("#system-history > li").first).to_contain_text("Changed")
    assert page.locator("#system-history time").first.get_attribute("datetime").endswith("+00:00")
    page.set_viewport_size({"width": 390, "height": 844})
    assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth")


@pytest.mark.parametrize("failure", ["network", "malformed", "unavailable", "redaction", "save"])
def test_history_failure_does_not_replace_current_health(page, client, db, failure):
    workspace(db)
    page.goto(URL)
    expect(page.locator("#system-history > li")).to_have_count(1)
    if failure == "save":
        db.execute(text("DROP TABLE system_observations"))
        db.commit()
    elif failure == "network":
        page.route("**" + HISTORY, lambda route: route.abort())
    else:
        data = client.get(HISTORY).json()
        if failure == "unavailable":
            data.update(status="UNAVAILABLE", entries=[])
        elif failure == "redaction":
            data["entries"][0]["state"] = "<img src=x onerror=alert(1)>private-raw-error"
        else:
            data = {"entries": []}
        page.route("**" + HISTORY, lambda route: route.fulfill(
            status=200, content_type="application/json", body=json.dumps(data),
        ))
    page.locator("#system-refresh").click()
    expect(page.locator("#system-refresh")).to_be_enabled()
    expect(page.locator("#system-status")).to_have_attribute("data-state", "NORMAL")
    expect(page.locator("#system-history > li")).to_have_count(0)
    expect(page.locator("#system-history-note")).to_contain_text("could not")
    if failure == "save":
        expect(page.locator("#system-history-note")).to_contain_text("could not be saved")
    assert "private-raw-error" not in page.locator("main").inner_text()


@pytest.mark.parametrize("inactive", [False, True])
def test_history_auth_failure_clears_all_evidence(page, db, inactive):
    workspace(db)
    page.goto(URL)
    expect(page.locator("#system-history > li")).to_have_count(1)
    headers = {"X-Serenity-Account-Status": "inactive"} if inactive else {}
    page.route("**" + HISTORY, lambda route: route.fulfill(
        status=403 if inactive else 401, headers=headers,
        content_type="application/json", body='{"detail":"Sign in required"}',
    ))
    page.locator("#system-refresh").click()
    expect(page.locator(".session-recovery")).to_be_visible()
    assert page.locator("#system-history > li").count() == 0