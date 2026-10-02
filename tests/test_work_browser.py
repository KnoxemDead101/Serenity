"""Real Chromium journeys over the disposable in-memory authenticated test app."""

import pytest

playwright = pytest.importorskip("playwright.sync_api")
expect = playwright.expect

from test_work import create, goal, ROOT

BASE = "http://testserver"


@pytest.mark.parametrize("family", ["projects", "tasks"])
def test_work_browser_create_edit_status_archive_restore_and_details(page, client, family):
    page.on("dialog", lambda dialog: dialog.accept())
    page.goto(f"{BASE}/{family}")
    form = page.locator("#work-form")
    expect(form.locator("[name=priority]")).to_have_value("NORMAL")
    form.locator("[name=name]").fill("Actionable work")
    form.locator("[name=description]").fill("<img src=x onerror=alert(1)>")
    form.locator("[name=date]").fill("2027-02-03")
    form.locator("[name=notes]").fill("Private work notes")
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("added.")
    record = client.get(f"{ROOT}/{family}").json()[0]
    row = page.locator(f'#work-body tr[data-record-id="{record["id"]}"]')
    expect(row).to_contain_text("<img src=x onerror=alert(1)>")
    assert page.locator("#work-body img").count() == 0
    row.locator('[data-action="edit"]').click()
    form.locator("[name=name]").fill("Discard edit")
    form.locator("#work-cancel").click()
    expect(form.locator("[name=name]")).to_have_value("")
    row.locator('[data-action="edit"]').click()
    form.locator("[name=name]").fill("Revised work")
    form.locator("[name=date]").fill("")
    form.locator("[name=notes]").fill("")
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("saved.")
    assert client.get(f"{ROOT}/{family}/{record['id']}").json()["notes"] is None
    row.locator(".work-status-select").select_option("COMPLETED")
    expect(page.locator("#work-message")).to_contain_text("status updated.")
    assert client.get(f"{ROOT}/{family}/{record['id']}").json()["completed_at"] is not None
    row.locator('[data-action="open"]').click()
    expect(page.locator("#work-details")).to_be_visible()
    expect(page.locator("#work-details")).to_contain_text("Revised work")
    page.locator("#work-details .work-details-status").select_option("PAUSED")
    expect(row.locator(".work-status-select")).to_have_value("PAUSED")
    page.locator('#work-details [data-action="close"]').click()
    row.locator('[data-action="deactivate"]').click()
    expect(page.locator("#work-message")).to_contain_text("archived.")
    expect(row).to_have_count(0)
    page.locator("#work-show-archived").check()
    expect(row).to_contain_text("Archived")
    expect(row.locator('[data-action="edit"]')).to_be_disabled()
    row.locator('[data-action="reactivate"]').click()
    expect(page.locator("#work-message")).to_contain_text("reactivated.")
    expect(row.locator('[data-action="edit"]')).to_be_enabled()
    page.reload()
    expect(row).to_contain_text("Revised work")


def test_work_browser_goal_project_task_source_navigation_and_archived_parent(page, client):
    source = goal(client)
    project = create(client, "projects", name="Source project", goal_id=source["id"])
    create(client, "projects", name="Unrelated")
    task = create(client, "tasks", name="Linked action", project_id=project["id"])
    create(client, "tasks", name="Standalone action")
    page.goto(f"{BASE}/goals?goal_id={source['id']}")
    expect(page.locator("#composition")).to_be_visible()
    page.locator(".goal-details-projects-link").click()
    expect(page.locator("#work-filter-parent")).to_have_value(str(source["id"]))
    expect(page.locator("#work-body tr")).to_have_count(1)
    page.locator('#work-body [data-action="open"]').click()
    page.locator(".work-tasks-link").click()
    expect(page.locator("#work-filter-parent")).to_have_value(str(project["id"]))
    expect(page.locator("#work-body tr")).to_have_count(1)
    expect(page.locator('#work-form [name=parent_id]')).to_have_value(str(project["id"]))
    page.locator('#work-body [data-action="open"]').click()
    page.locator("#work-details .work-parent-link").click()
    expect(page.locator("#work-details-title")).to_have_text("Project: Source project")
    page.locator("#work-details .work-parent-link").click()
    expect(page.locator("#composition")).to_be_visible()
    client.post(f"{ROOT}/projects/{project['id']}/deactivate")
    page.goto(f"{BASE}/tasks?project_id={project['id']}")
    row = page.locator(f'#work-body tr[data-record-id="{task["id"]}"]')
    expect(row.locator('[data-action="edit"]')).to_be_disabled()
    expect(row.locator(".work-status-select")).to_be_disabled()
    expect(page.locator('#work-form [name=parent_id]')).to_have_value("")


def test_work_browser_validation_preserves_input_and_mobile_navigation(page, client):
    page.set_viewport_size({"width": 390, "height": 844})
    page.goto(BASE + "/projects")
    expect(page.locator('#work-form [name=priority]')).to_have_value("NORMAL")
    form = page.locator("#work-form")
    form.locator("[name=name]").fill("Do not discard")
    # Invalid date passes the browser's date input but is rejected by Pydantic.
    form.locator("[name=date]").fill("10000-01-01")
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_be_visible()
    expect(page.locator("#work-message")).to_contain_text("date")
    expect(form.locator("[name=name]")).to_have_value("Do not discard")
    assert client.get(ROOT + "/projects").json() == []
    page.locator(".nav-toggle").click()
    expect(page.locator("#site-nav")).to_be_visible()
    page.locator('#site-nav a[href="/tasks"]').click()
    expect(page.locator("h1")).to_have_text("Tasks")


def test_work_browser_optional_associations_can_be_created_changed_and_cleared(page, client):
    source = goal(client)
    alternate = goal(client)
    page.goto(BASE + "/projects")
    form = page.locator("#work-form")
    expect(form.locator("[name=priority]")).to_have_value("NORMAL")
    form.locator("[name=name]").fill("Linked through form")
    form.locator("[name=parent_id]").select_option(str(source["id"]))
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("added.")
    project = client.get(ROOT + "/projects").json()[0]
    assert project["goal_id"] == source["id"]
    row = page.locator(f'#work-body tr[data-record-id="{project["id"]}"]')
    row.locator('[data-action="edit"]').click()
    form.locator("[name=parent_id]").select_option(str(alternate["id"]))
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("saved.")
    assert client.get(f"{ROOT}/projects/{project['id']}").json()["goal_id"] == alternate["id"]
    row.locator('[data-action="edit"]').click()
    form.locator("[name=parent_id]").select_option("")
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("saved.")
    expect(row).to_contain_text("Standalone")
    page.goto(BASE + "/tasks")
    expect(form.locator("[name=priority]")).to_have_value("NORMAL")
    form.locator("[name=name]").fill("A linked action")
    form.locator("[name=parent_id]").select_option(str(project["id"]))
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("added.")
    task = client.get(ROOT + "/tasks").json()[0]
    assert task["project_id"] == project["id"]
    page.locator('#work-body [data-action="edit"]').click()
    form.locator("[name=parent_id]").select_option("")
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("saved.")
    assert client.get(f"{ROOT}/tasks/{task['id']}").json()["project_id"] is None


def test_work_browser_load_failure_retry_and_inaccessible_source(page, client):
    page.route("**/serenity-api/projects?*", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"Unavailable"}',
    ))
    page.goto(BASE + "/projects")
    expect(page.locator("#work-load-error")).to_be_visible()
    expect(page.locator("#work-load-error-text")).to_contain_text("Unavailable")
    page.unroute("**/serenity-api/projects?*")
    page.locator("#work-retry").click()
    expect(page.locator("#work-load-error")).to_be_hidden()
    expect(page.locator("#work-body")).to_contain_text("No active projects")
    page.goto(BASE + "/projects?goal_id=999999")
    expect(page.locator("#work-load-error-text")).to_contain_text("could not be found")


def test_work_browser_refresh_failure_after_save_does_not_invite_duplicate_create(page, client):
    page.goto(BASE + "/tasks")
    form = page.locator("#work-form")
    expect(form.locator("[name=priority]")).to_have_value("NORMAL")
    page.route("**/serenity-api/tasks?*", lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"Unavailable"}',
    ))
    form.locator("[name=name]").fill("Saved once")
    form.locator("#work-submit").click()
    expect(page.locator("#work-message")).to_contain_text("Task added. The list could not refresh.")
    expect(form.locator("[name=name]")).to_have_value("")
    assert len(client.get(ROOT + "/tasks").json()) == 1
    page.unroute("**/serenity-api/tasks?*")
    page.locator("#work-retry").click()
    expect(page.locator("#work-body")).to_contain_text("Saved once")