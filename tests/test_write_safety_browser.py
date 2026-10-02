"""Read-only banner and client-side refusal, using synthetic signed-in fixtures."""

import json

from playwright.sync_api import expect

from services.write_safety import MESSAGE


def test_read_only_banner_blocks_saving_without_hiding_existing_reads(page, client):
    page.route("**/serenity-api/system/write-safety", lambda route: route.fulfill(
        status=200, content_type="application/json",
        body=json.dumps({"state": "READ_ONLY", "writes_enabled": False, "message": MESSAGE}),
    ))
    before = client.get("/serenity-api/goals").json()
    page.goto("http://serenity.test/goals")
    expect(page.locator("#write-safety-banner")).to_have_text(MESSAGE)
    form = page.locator("#goal-form")
    form.locator("[name=name]").fill("Must not save")
    form.locator("[name=goal_type]").select_option("SAVINGS")
    form.locator("[name=category]").select_option("FINANCIAL")
    form.get_by_role("button", name="Add goal", exact=True).click()
    expect(page.locator("#goal-message")).to_contain_text("temporarily read-only")
    assert client.get("/serenity-api/goals").json() == before


def test_unavailable_safety_check_does_not_assume_writes_are_safe(page):
    page.route("**/serenity-api/system/write-safety", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"Unavailable"}',
    ))
    page.goto("http://serenity.test/goals")
    expect(page.locator("#write-safety-banner")).to_contain_text(
        "Write safety could not be verified"
    )