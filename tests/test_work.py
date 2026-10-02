"""Work lifecycle and ownership, with financial invariance as an explicit gate."""

from contextlib import contextmanager

import pytest
from pydantic import ValidationError
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from auth import require_session
from main import app
from models.work import Project, Task
from schemas.work import ProjectFields, TaskFields
from services import work_service
from services.ownership import MissingOwnerError

ROOT = "/serenity-api"


@contextmanager
def workspace(owner):
    previous = app.dependency_overrides[require_session]
    app.dependency_overrides[require_session] = lambda: owner
    try:
        yield
    finally:
        app.dependency_overrides[require_session] = previous


def create(client, family, **fields):
    response = client.post(f"{ROOT}/{family}", json={"name": f"Test {family}", **fields})
    assert response.status_code == 201, response.text
    return response.json()


def goal(client):
    response = client.post(f"{ROOT}/goals", json={
        "name": "Source goal", "goal_type": "SAVINGS", "category": "FINANCIAL",
        "target_amount": "1000.00", "current_progress_amount": "12.34",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("family,date_field", [("projects", "target_date"), ("tasks", "due_date")])
def test_work_standalone_full_edit_lifecycle_and_utc(client, family, date_field):
    record = create(client, family, name="  Readable work  ", **{date_field: "2027-01-03"})
    url = f"{ROOT}/{family}/{record['id']}"
    assert record["name"] == "Readable work"
    assert record["status"] == "NOT_STARTED"
    assert record["completed_at"] is None
    assert record["created_at"].endswith("Z")
    assert "owner_id" not in record
    assert client.get(url).json() == record
    updated = client.put(url, json={"name": "Changed", "description": "  Notes  "}).json()
    assert updated[date_field] is None
    assert updated["description"] == "Notes"
    assert updated["notes"] is None
    for status in ["IN_PROGRESS", "COMPLETED", "COMPLETED", "PAUSED", "CANCELLED", "NOT_STARTED"]:
        response = client.post(f"{url}/status", json={"status": status})
        assert response.status_code == 200, response.text
        row = response.json()
        assert (row["completed_at"] is not None) == (status == "COMPLETED")
        if status == "COMPLETED":
            assert row["completed_at"].endswith("Z")
            if record.get("completed_at"):
                assert row["completed_at"] == record["completed_at"]
        record = row
    client.post(f"{url}/deactivate")
    assert client.get(f"{ROOT}/{family}").json() == []
    assert len(client.get(f"{ROOT}/{family}?active_only=false").json()) == 1
    assert client.put(url, json={"name": "No"}).status_code == 409
    assert client.post(f"{url}/status", json={"status": "COMPLETED"}).status_code == 409
    assert client.post(f"{url}/reactivate").json()["active"] is True


@pytest.mark.parametrize("family,link", [("projects", "goal_id"), ("tasks", "project_id")])
@pytest.mark.parametrize("fields", [
    {"owner_id": "hacker"}, {"active": False}, {"status": "COMPLETED"},
    {"completed_at": "2026-01-01T00:00:00Z"}, {"created_at": "2026-01-01T00:00:00Z"},
    {"target_amount": "1.00"}, {"progress_source": "ACTUAL"}, {"name": " "},
    {"priority": "URGENT"}, {"description": "x" * 1001},
])
def test_work_rejects_protected_financial_and_invalid_fields(client, family, link, fields):
    assert client.post(f"{ROOT}/{family}", json={"name": "Valid", **fields}).status_code == 422
    row = create(client, family)
    assert client.put(f"{ROOT}/{family}/{row['id']}", json={"name": "Valid", **fields}).status_code == 422


@pytest.mark.parametrize("family,link", [("projects", "goal_id"), ("tasks", "project_id")])
@pytest.mark.parametrize("value", [0, -1, True, "1", 1.5, 2147483648])
def test_work_link_ids_are_strict_positive_integers(client, family, link, value):
    assert client.post(f"{ROOT}/{family}", json={"name": "Valid", link: value}).status_code == 422


def test_work_source_links_owner_scope_and_goal_delete_conflict(client):
    source = goal(client)
    project = create(client, "projects", goal_id=source["id"])
    task = create(client, "tasks", project_id=project["id"])
    assert project["goal_name"] == source["name"]
    assert task["project_name"] == project["name"]
    assert client.get(f"{ROOT}/projects?goal_id={source['id']}").json() == [project]
    assert client.get(f"{ROOT}/tasks?project_id={project['id']}").json() == [task]
    with workspace("other-workspace"):
        for family, record in [("projects", project), ("tasks", task)]:
            url = f"{ROOT}/{family}/{record['id']}"
            assert client.get(f"{ROOT}/{family}?active_only=false").json() == []
            assert client.get(url).status_code == 404
            assert client.put(url, json={"name": "No access"}).status_code == 404
            for action in ["deactivate", "reactivate", "status"]:
                assert client.post(f"{url}/{action}", json={"status": "COMPLETED"} if action == "status" else None).status_code == 404
        assert client.post(f"{ROOT}/projects", json={"name": "No", "goal_id": source["id"]}).status_code == 404
        assert client.post(f"{ROOT}/tasks", json={"name": "No", "project_id": project["id"]}).status_code == 404
        assert client.get(f"{ROOT}/projects?goal_id={source['id']}").status_code == 404
        assert client.get(f"{ROOT}/tasks?project_id={project['id']}").status_code == 404
        other_goal = goal(client)
        other_project = create(client, "projects")
        exported = client.get(f"{ROOT}/export").json()
        assert exported["tasks"] == []
        assert all(row["id"] != project["id"] for row in exported["projects"])
    assert client.put(f"{ROOT}/projects/{project['id']}", json={"name": "No", "goal_id": other_goal["id"]}).status_code == 404
    assert client.put(f"{ROOT}/tasks/{task['id']}", json={"name": "No", "project_id": other_project["id"]}).status_code == 404
    client.post(f"{ROOT}/projects/{project['id']}/deactivate")
    assert client.delete(f"{ROOT}/goals/{source['id']}").status_code == 409
    client.post(f"{ROOT}/projects/{project['id']}/reactivate")
    assert client.put(f"{ROOT}/projects/{project['id']}", json={"name": "Unlinked", "goal_id": None}).status_code == 200
    assert client.delete(f"{ROOT}/goals/{source['id']}").status_code == 204


def test_archived_source_policy_preserves_work_and_never_cascades(client):
    source = goal(client)
    project = create(client, "projects", goal_id=source["id"])
    task = create(client, "tasks", project_id=project["id"])
    client.post(f"{ROOT}/goals/{source['id']}/deactivate")
    assert client.post(f"{ROOT}/projects", json={"name": "New", "goal_id": source["id"]}).status_code == 409
    assert client.put(f"{ROOT}/projects/{project['id']}", json={"name": "Keep link", "goal_id": source["id"]}).status_code == 200
    client.post(f"{ROOT}/projects/{project['id']}/deactivate")
    url = f"{ROOT}/tasks/{task['id']}"
    assert client.get(url).json()["active"] is True
    assert client.get(url).json()["status"] == "NOT_STARTED"
    assert client.put(url, json={"name": "Cannot detach behind archived source"}).status_code == 409
    for action in ["status", "deactivate", "reactivate"]:
        assert client.post(f"{url}/{action}", json={"status": "COMPLETED"} if action == "status" else None).status_code == 409
    assert client.post(f"{ROOT}/tasks", json={"name": "New", "project_id": project["id"]}).status_code == 409
    client.post(f"{ROOT}/projects/{project['id']}/reactivate")
    assert client.post(f"{url}/status", json={"status": "COMPLETED"}).status_code == 200
    assert client.get(f"{ROOT}/projects/{project['id']}").json()["status"] == "NOT_STARTED"
    assert client.get(f"{ROOT}/goals/{source['id']}").json()["current_progress_amount_cents"] == 1234


def test_work_cannot_change_actual_finances_goal_items_or_reserved_progress(client):
    account = client.post(f"{ROOT}/accounts", json={
        "name": "Savings", "account_type": "Checking", "classification": "Personal",
        "opening_balance": "234.56",
    }).json()
    client.post(f"{ROOT}/accounts/{account['id']}/transactions", json={
        "date": "2026-10-02", "transaction_type": "Income", "amount": "10.00",
        "description": "Actual deposit",
    })
    source = goal(client)
    paths = ["/dashboard/summary", "/accounts", f"/accounts/{account['id']}/transactions",
             f"/goals/{source['id']}/composition"]
    before = {path: client.get(ROOT + path).json() for path in paths}
    assert all(client.get(ROOT + path).status_code == 200 for path in paths)
    export_before = client.get(f"{ROOT}/export").json()
    project = create(client, "projects", goal_id=source["id"])
    task = create(client, "tasks", project_id=project["id"])
    for family, record in [("tasks", task), ("projects", project)]:
        url = f"{ROOT}/{family}/{record['id']}"
        assert client.post(url + "/status", json={"status": "COMPLETED"}).status_code == 200
        assert client.post(url + "/deactivate").status_code == 200
    assert {path: client.get(ROOT + path).json() for path in paths} == before
    exported = client.get(f"{ROOT}/export").json()
    assert exported["format_version"] == export_before["format_version"]
    for key in ["accounts", "transactions", "goals", "debts", "investments", "bills"]:
        assert exported[key] == export_before[key]
    assert exported["projects"][0]["active"] is False
    assert exported["tasks"][0]["active"] is False


def test_work_direct_services_require_owner_and_validate_payloads(db):
    for model, schema in [(Project, ProjectFields), (Task, TaskFields)]:
        with pytest.raises(MissingOwnerError):
            work_service.create_work(db, model, schema(name="Work"), "")
        with pytest.raises(ValidationError):
            schema(name="Work", owner_id="fake")


@pytest.mark.parametrize("family,parent,link", [
    ("projects", "goals", "goal_id"), ("tasks", "projects", "project_id"),
])
def test_default_sqlite_raw_relationship_guards(client, db, family, parent, link):
    source = goal(client) if parent == "goals" else create(client, "projects")
    record = create(client, family, **{link: source["id"]})
    assert db.scalar(text("PRAGMA foreign_keys")) == 0
    statements = [
        (f"UPDATE {family} SET owner_id = 'foreign' WHERE id=:id", {"id": record["id"]}),
        (f"UPDATE {family} SET {link}=999999 WHERE id=:id", {"id": record["id"]}),
        (f"DELETE FROM {parent} WHERE id=:id", {"id": source["id"]}),
        (f"UPDATE {parent} SET owner_id='foreign' WHERE id=:id", {"id": source["id"]}),
        (f"INSERT INTO {family} (owner_id,name,{link},created_at,updated_at) "
         "VALUES ('foreign','Invalid',:id,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", {"id": source["id"]}),
    ]
    for sql, params in statements:
        with pytest.raises(IntegrityError):
            db.execute(text(sql), params)
            db.commit()
        db.rollback()


@pytest.mark.parametrize("family", ["projects", "tasks"])
def test_work_requires_sign_in_for_all_routes(real_auth_client, family):
    assert real_auth_client.get(f"/{family}", follow_redirects=False).status_code == 307
    for method, path, payload in [
        ("GET", "", None), ("GET", "/options", None), ("GET", "/1", None),
        ("POST", "", {"name": "No"}), ("PUT", "/1", {"name": "No"}),
        ("POST", "/1/status", {"status": "COMPLETED"}),
        ("POST", "/1/deactivate", None), ("POST", "/1/reactivate", None),
    ]:
        assert real_auth_client.request(method, f"{ROOT}/{family}{path}", json=payload).status_code == 401