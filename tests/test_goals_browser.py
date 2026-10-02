"""Signed-in browser proof for standalone Goal Core on synthetic fixture data."""

import pytest
from playwright.sync_api import expect

BASE = "http://serenity.test/goals"
API = "/serenity-api/goals"


def _form(page):
    return page.locator("#goal-form")


def _add_goal(page, name="Emergency fund", goal_type="SAVINGS", category="FINANCIAL"):
    form = _form(page)
    form.locator("[name=name]").fill(name)
    form.locator("[name=goal_type]").select_option(goal_type)
    form.locator("[name=category]").select_option(category)
    form.get_by_role("button", name="Add goal", exact=True).click()
    expect(page.locator("#goal-message")).to_have_text("Goal added.")
    return page.locator("#goals-body tr").filter(has_text=name)


def test_goal_browser_create_edit_clear_nulls_and_cancel(page, client):
    page.goto(BASE)
    expect(page.get_by_role("heading", name="Goals", exact=True)).to_be_visible()
    expect(page.locator("#goals-body")).to_contain_text("No active goals")
    expect(_form(page).locator("[name=status]")).to_be_disabled()
    _form(page).locator("[name=target_amount]").fill("999999999999.99")
    _form(page).locator("[name=current_progress_amount]").fill("123.45")
    _form(page).locator("[name=target_date]").fill("2027-06-01")
    row = _add_goal(page)
    created = client.get(API).json()[0]
    assert created["target_amount_cents"] == 99999999999999
    assert created["current_progress_amount_cents"] == 12345
    assert created["status"] == "NOT_STARTED"
    assert created["completed_at"] is None

    row.get_by_role("button", name="Edit", exact=True).click()
    expect(_form(page).locator("[name=target_amount]")).to_have_value("999999999999.99")
    _form(page).locator("[name=name]").fill("Discard this edit")
    _form(page).get_by_role("button", name="Cancel edit").click()
    expect(_form(page).locator("[name=name]")).to_have_value("")
    expect(row).to_contain_text("Emergency fund")

    row.get_by_role("button", name="Edit", exact=True).click()
    _form(page).locator("[name=description]").fill("Reviewed manually")
    _form(page).locator("[name=notes]").fill("Private plan")
    for field in ("target_amount", "current_progress_amount", "target_date"):
        _form(page).locator(f"[name={field}]").fill("")
    _form(page).get_by_role("button", name="Save goal").click()
    expect(page.locator("#goal-message")).to_have_text("Goal saved.")
    saved = client.get(f"{API}/{created['id']}").json()
    assert saved["description"] == "Reviewed manually"
    assert saved["notes"] == "Private plan"
    assert saved["target_date"] is None
    assert saved["target_amount"] is None
    assert saved["current_progress_amount"] is None
    assert saved["status"] == "NOT_STARTED"


def test_goal_browser_status_archive_reactivate_and_permanent_delete(page, client):
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(BASE)
    row = _add_goal(page, "Career course", "NONFINANCIAL", "CAREER")
    goal_id = client.get(API).json()[0]["id"]
    row = page.locator(f'#goals-body tr[data-goal-id="{goal_id}"]')
    for status in ("IN_PROGRESS", "COMPLETED", "PAUSED", "CANCELLED", "NOT_STARTED"):
        with page.expect_response(
            lambda response: response.url.endswith(f"/goals/{goal_id}/status")
            and response.request.method == "POST"
        ) as changed:
            row.locator(".goal-status-select").select_option(status)
        assert changed.value.status == 200
        expect(page.locator("#goal-message")).to_have_text("Career course status updated.")
        record = client.get(f"{API}/{goal_id}").json()
        assert record["status"] == status
        assert (record["completed_at"] is not None) == (status == "COMPLETED")
        expect(row.locator(".goal-status-select")).to_have_value(status)

    row.get_by_role("button", name="Archive", exact=True).click()
    expect(page.locator("#goal-message")).to_have_text("Career course archived.")
    assert client.get(API).json() == []
    page.locator("#goals-show-archived").check()
    expect(row).to_contain_text("Archived")
    row.get_by_role("button", name="Reactivate", exact=True).click()
    expect(page.locator("#goal-message")).to_have_text("Career course reactivated.")
    assert client.get(f"{API}/{goal_id}").json()["active"] is True
    row.get_by_role("button", name="Delete", exact=True).click()
    expect(page.locator("#goal-message")).to_have_text("Career course deleted.")
    assert client.get(f"{API}/{goal_id}").status_code == 404


def test_goal_browser_reserved_progress_and_safe_text_display(page, client):
    page.goto(BASE)
    _form(page).locator("[name=progress_source]").select_option("ACCOUNT_BALANCE")
    _form(page).locator("[name=description]").fill("<img src=x onerror=alert(1)>")
    row = _add_goal(page, "Manual review")
    expect(row).to_contain_text("reserved; not linked")
    expect(row).to_contain_text("<img src=x onerror=alert(1)>")
    assert row.locator("img").count() == 0
    goal = client.get(API).json()[0]
    assert goal["current_progress_amount"] is None
    assert goal["status"] == "NOT_STARTED"
    assert client.get("/serenity-api/accounts").json() == []


def test_goal_browser_progress_input_is_manual_only_on_create_and_edit(page, client):
    page.goto(BASE)
    expect(page.locator("#goals-body")).to_contain_text("No active goals")
    form = _form(page)
    source = form.locator("[name=progress_source]")
    amount = form.locator("[name=current_progress_amount]")
    expect(source.locator("option")).to_have_count(8)
    expect(amount).to_be_enabled()
    for reserved in (
        "TRANSACTION_ACTIVITY", "ACCOUNT_BALANCE", "DEBT_BALANCE",
        "PORTFOLIO_VALUE", "INVESTMENT_ACCOUNT", "BUSINESS_METRIC", "MILESTONES",
    ):
        source.select_option(reserved)
        expect(amount).to_be_disabled()
    source.select_option("MANUAL")
    expect(amount).to_be_enabled()
    amount.fill("27.36")
    source.select_option("ACCOUNT_BALANCE")
    expect(amount).to_be_disabled()
    expect(amount).to_have_value("27.36")
    form.locator("[name=name]").fill("Manual-only progress")
    form.get_by_role("button", name="Add goal", exact=True).click()
    expect(page.locator("#goal-message")).to_contain_text("only be set when progress source is MANUAL")
    assert client.get(API).json() == []

    source.select_option("MANUAL")
    amount.fill("")
    source.select_option("ACCOUNT_BALANCE")
    row = _add_goal(page, "Manual-only progress")
    saved = client.get(API).json()[0]
    assert saved["progress_source"] == "ACCOUNT_BALANCE"
    assert saved["current_progress_amount"] is None
    row.get_by_role("button", name="Edit", exact=True).click()
    expect(amount).to_be_disabled()
    source.select_option("MANUAL")
    expect(amount).to_be_enabled()
    amount.fill("0.00")
    form.get_by_role("button", name="Save goal").click()
    expect(page.locator("#goal-message")).to_have_text("Goal saved.")
    saved = client.get(f"{API}/{saved['id']}").json()
    assert saved["progress_source"] == "MANUAL"
    assert saved["current_progress_amount_cents"] == 0

    row.get_by_role("button", name="Edit", exact=True).click()
    source.select_option("PORTFOLIO_VALUE")
    expect(amount).to_be_disabled()
    expect(amount).to_have_value("0.00")
    form.get_by_role("button", name="Save goal").click()
    expect(page.locator("#goal-message")).to_contain_text("only be set when progress source is MANUAL")
    assert client.get(f"{API}/{saved['id']}").json() == saved
    form.get_by_role("button", name="Cancel edit").click()
    expect(source).to_have_value("MANUAL")
    expect(amount).to_be_enabled()


def test_goal_browser_validation_and_failed_write_leave_form_visible(page, client):
    page.goto(BASE)
    form = _form(page)
    form.locator("[name=name]").fill("Bounded goal")
    form.locator("[name=target_amount]").fill("1000000000000.01")
    form.get_by_role("button", name="Add goal", exact=True).click()
    expect(page.locator("#goal-message")).to_contain_text("too large")
    assert client.get(API).json() == []
    expect(form.locator("[name=name]")).to_have_value("Bounded goal")
    form.locator("[name=target_amount]").fill("10.005")
    form.get_by_role("button", name="Add goal", exact=True).click()
    expect(page.locator("#goal-message")).to_contain_text("plain dollars")
    assert client.get(API).json() == []


@pytest.mark.parametrize("width", [390, 1280])
def test_goals_page_responsive_layout_and_native_navigation(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(BASE)
    expect(page.get_by_role("heading", name="Goals", exact=True)).to_be_visible()
    if width == 390:
        page.get_by_role("button", name="Menu", exact=True).click()
    expect(page.locator('.site-nav a[href="/goals"]')).to_be_visible()
    assert page.locator('a[aria-current="page"]').get_attribute("href") == "/goals"
    _add_goal(page, "Responsive goal")
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )


@pytest.mark.parametrize("route", ["/", "/accounts", "/finances", "/income", "/setup",
                                   "/profit-engine", "/portfolios"])
def test_existing_pages_link_to_the_new_goal_core_page(page, route):
    page.goto(f"http://serenity.test{route}")
    expect(page.locator('.site-nav a[href="/goals"]')).to_have_text("Goals")


def test_goal_browser_session_recovery_clears_private_goal_data(page, client):
    page.goto(BASE)
    _add_goal(page, "Private goal")

    def expired(route):
        route.fulfill(status=401, content_type="application/json",
                      body='{"detail":"Sign in required"}')

    page.route("**/serenity-api/goals*", expired)
    # Recovery removes this checkbox immediately, so do not ask Playwright to
    # verify its checked state after triggering the expired-session response.
    page.locator("#goals-show-archived").click()
    expect(page.get_by_role("heading", name="Your session has ended")).to_be_visible()
    assert page.locator("#goal-form").count() == 0
    assert page.get_by_text("Private goal", exact=True).count() == 0