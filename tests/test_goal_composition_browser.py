"""Synthetic signed-in browser coverage for Goal Composition's real API flows."""

import pytest
from playwright.sync_api import expect


BASE = "http://serenity.test/goals"
API = "/serenity-api/goals"


def _create_goal(page, name="Composition browser goal"):
    form = page.locator("#goal-form")
    form.locator("[name=name]").fill(name)
    form.locator("[name=goal_type]").select_option("SAVINGS")
    form.locator("[name=category]").select_option("FINANCIAL")
    form.locator("[name=current_progress_amount]").fill("100.00")
    form.get_by_role("button", name="Add goal", exact=True).click()
    expect(page.locator("#goal-message")).to_have_text("Goal added.")
    row = page.locator("#goals-body tr").filter(has_text=name)
    return row, form


def _composition_form(page, kind):
    return page.locator(f'#composition-body form[data-kind="{kind}"]')


def test_composition_browser_create_edit_sort_status_archive_checkpoint_and_cleanup(
    page, client,
):
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(BASE)
    goal_row, parent_form = _create_goal(page)
    goal_id = client.get(API).json()[0]["id"]
    goal_row.locator('button[data-action="open"]').click()
    panel = page.locator("#composition")
    expect(panel).to_be_visible()

    items = _composition_form(page, "items")
    items.locator("[name=name]").fill("Later item")
    items.locator("[name=expected_cost]").fill("20.00")
    items.locator("[name=manual_actual_cost_override]").fill("15.00")
    items.locator("[name=sort_order]").fill("5")
    items.get_by_role("button", name="Add item").click()
    expect(page.locator("#composition-message")).to_have_text("Item added.")
    later = client.get(f"{API}/{goal_id}/items").json()[0]
    assert later["expected_cost_cents"] == 2000
    assert later["manual_actual_cost_override_cents"] == 1500
    later_row = page.locator(
        f'#composition-body [data-section="items"] tr[data-record-id="{later["id"]}"]'
    )
    later_row.get_by_role("button", name="Edit").click()
    edit = _composition_form(page, "items")
    edit.locator("[name=name]").fill("Reordered item")
    edit.locator("[name=sort_order]").fill("0")
    edit.get_by_role("button", name="Save item").click()
    expect(page.locator("#composition-message")).to_have_text("Item saved.")
    later = client.get(f"{API}/{goal_id}/items").json()[0]

    item_status = page.locator(
        f'.composition-status[data-kind="items"][data-id="{later["id"]}"]'
    )
    item_status.select_option("COMPLETED")
    expect(page.locator("#composition-message")).to_have_text("Status updated.")
    assert client.get(f"{API}/{goal_id}/items/{later['id']}").json()["status"] == "COMPLETED"
    item_row = page.locator(
        f'#composition-body [data-section="items"] tr[data-record-id="{later["id"]}"]'
    )
    item_row.get_by_role("button", name="Archive").click()
    expect(page.locator("#composition-message")).to_have_text("Item archived.")
    page.locator("#composition-show-archived").check()
    expect(item_row).to_contain_text("Archived")
    item_row.get_by_role("button", name="Reactivate").click()
    expect(page.locator("#composition-message")).to_have_text("Item reactivated.")

    milestone_form = _composition_form(page, "milestones")
    milestone_form.locator("[name=title]").fill("First milestone")
    milestone_form.locator("[name=sort_order]").fill("2")
    milestone_form.get_by_role("button", name="Add milestone").click()
    expect(page.locator("#composition-message")).to_have_text("Milestone added.")
    milestone = client.get(f"{API}/{goal_id}/milestones").json()[0]
    page.locator(
        f'.composition-status[data-kind="milestones"][data-id="{milestone["id"]}"]'
    ).select_option("COMPLETED")
    expect(page.locator("#composition-message")).to_have_text("Status updated.")
    assert client.get(
        f"{API}/{goal_id}/milestones/{milestone['id']}"
    ).json()["completed_at"] is not None

    checkpoint_form = _composition_form(page, "checkpoints")
    checkpoint_form.locator("[name=amount]").fill("250.00")
    checkpoint_form.locator("[name=label]").fill("Halfway")
    checkpoint_form.get_by_role("button", name="Add checkpoint").click()
    expect(page.locator("#composition-message")).to_have_text("Checkpoint added.")
    checkpoint = client.get(f"{API}/{goal_id}/checkpoints").json()[0]
    checkpoint_row = page.locator(
        f'#composition-body [data-section="checkpoints"] tr[data-record-id="{checkpoint["id"]}"]'
    )
    expect(checkpoint_row).to_contain_text("Not reached")
    assert checkpoint["reached"] is False

    # Editing the parent goal updates the server-derived checkpoint state.
    goal_row.locator('button[data-action="edit"]').click()
    parent_form.locator("[name=current_progress_amount]").fill("300.00")
    parent_form.get_by_role("button", name="Save goal").click()
    expect(page.locator("#goal-message")).to_have_text("Goal saved.")
    expect(checkpoint_row).to_contain_text("Reached")
    assert client.get(f"{API}/{goal_id}/checkpoints/{checkpoint['id']}").json()["reached"] is True

    # Parents with any child are retained; all children are explicitly removed.
    goal_row.locator('button[data-action="delete"]').click()
    expect(page.locator("#goal-message")).to_contain_text("milestones")
    assert client.get(f"{API}/{goal_id}").status_code == 200
    checkpoint_row.get_by_role("button", name="Delete").click()
    expect(page.locator("#composition-message")).to_have_text("Checkpoint deleted.")
    milestone_row = page.locator(
        f'#composition-body [data-section="milestones"] tr[data-record-id="{milestone["id"]}"]'
    )
    milestone_row.get_by_role("button", name="Delete").click()
    expect(page.locator("#composition-message")).to_have_text("Milestone deleted.")
    item_row.get_by_role("button", name="Delete").click()
    expect(page.locator("#composition-message")).to_have_text("Item deleted.")
    goal_row.locator('button[data-action="delete"]').click()
    expect(page.locator("#goal-message")).to_have_text("Composition browser goal deleted.")
    assert client.get(f"{API}/{goal_id}").status_code == 404


@pytest.mark.parametrize("width", [390, 1280])
def test_composition_layout_fits_phone_and_desktop_widths(page, width):
    page.set_viewport_size({"width": width, "height": 900})
    page.goto(BASE)
    if width == 390:
        page.get_by_role("button", name="Menu", exact=True).click()
    expect(page.get_by_role("heading", name="Goals", exact=True)).to_be_visible()
    assert page.evaluate(
        "document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1"
    )


def test_composition_session_recovery_removes_private_content(page, client):
    page.goto(BASE)
    row, _ = _create_goal(page, "Private composition")
    goal = client.get(API).json()[0]
    row.locator('button[data-action="open"]').click()
    expect(page.locator("#composition")).to_be_visible()
    item_form = _composition_form(page, "items")
    item_form.locator("[name=name]").fill("Sensitive child")
    item_form.get_by_role("button", name="Add item").click()
    expect(page.locator("#composition-body")).to_contain_text("Sensitive child")

    def expired(route):
        route.fulfill(
            status=401, content_type="application/json",
            body='{"detail":"Sign in required"}',
        )

    page.route("**/*", expired)
    page.locator("#composition-show-archived").click()
    expect(page.get_by_role("heading", name="Your session has ended")).to_be_visible()
    assert page.locator("#composition-body").count() == 0
    assert page.get_by_text("Sensitive child", exact=True).count() == 0
    assert goal["id"] > 0