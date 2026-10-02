"""Explicit Goal Composition authorization, transition, and race boundaries."""

from contextlib import contextmanager
from datetime import datetime
from threading import Event, Thread

import pytest
from sqlalchemy import event, text
from sqlalchemy.orm import sessionmaker

from auth import require_session
from main import app
from models.goal import Goal
from storage.database import Base, get_db


ROOT = "/serenity-api/goals"
STATUSES = ("PLANNED", "IN_PROGRESS", "COMPLETED", "SKIPPED", "CANCELLED")
MILESTONE_STATUSES = (
    "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "SKIPPED", "CANCELLED",
)
PARENT = {
    "name": "Boundary goal",
    "goal_type": "SAVINGS",
    "category": "FINANCIAL",
    "target_amount": "1000.00",
    "current_progress_amount": "100.00",
    "progress_source": "MANUAL",
}


def create_goal(client, **changes):
    response = client.post(ROOT, json={**PARENT, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def create_child(client, goal_id, kind, payload):
    response = client.post(f"{ROOT}/{goal_id}/{kind}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@contextmanager
def as_workspace(owner_id):
    previous = app.dependency_overrides.get(require_session)
    app.dependency_overrides[require_session] = lambda: owner_id
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(require_session, None)
        else:
            app.dependency_overrides[require_session] = previous


def child_setup(client, kind, goal_id):
    if kind == "items":
        value = create_child(client, goal_id, kind, {"name": "Private item"})
        return value, {
            "name": "Updated item", "description": None, "expected_cost": None,
            "manual_actual_cost_override": None, "notes": None, "sort_order": 4,
        }
    if kind == "milestones":
        value = create_child(client, goal_id, kind, {"title": "Private milestone"})
        return value, {
            "title": "Updated milestone", "description": None,
            "target_date": "2028-02-29", "sort_order": 4,
        }
    value = create_child(client, goal_id, kind, {"amount": "10.00"})
    return value, {"amount": "12.34", "label": "Updated checkpoint", "sort_order": 4}


def child_url(goal_id, kind, record_id):
    return f"{ROOT}/{goal_id}/{kind}/{record_id}"


def wrong_child_status(_kind):
    return "COMPLETED"


@pytest.mark.parametrize(("initial", "target"), [
    (initial, target) for initial in STATUSES for target in STATUSES
])
def test_item_all_status_transitions_preserve_completed_parent(initial, target, client):
    goal = create_goal(client)
    parent_complete = client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": "COMPLETED"},
    ).json()
    item = create_child(client, goal["id"], "items", {"name": "Transition item"})
    item_url = child_url(goal["id"], "items", item["id"])
    if initial != "PLANNED":
        response = client.post(f"{item_url}/status", json={"status": initial})
        assert response.status_code == 200, response.text
    parent_before = client.get(f"{ROOT}/{goal['id']}").json()
    assert parent_before == parent_complete

    response = client.post(f"{item_url}/status", json={"status": target})

    assert response.status_code == 200, response.text
    assert response.json()["status"] == target
    assert "completed_at" not in response.json()
    assert client.get(f"{ROOT}/{goal['id']}").json() == parent_before


@pytest.mark.parametrize(("initial", "target"), [
    (initial, target)
    for initial in MILESTONE_STATUSES for target in MILESTONE_STATUSES
])
def test_milestone_all_status_transitions_preserve_completed_parent(initial, target, client):
    goal = create_goal(client)
    parent_complete = client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": "COMPLETED"},
    ).json()
    milestone = create_child(
        client, goal["id"], "milestones", {"title": "Transition milestone"},
    )
    milestone_url = child_url(goal["id"], "milestones", milestone["id"])
    if initial != "NOT_STARTED":
        response = client.post(
            f"{milestone_url}/status", json={"status": initial},
        )
        assert response.status_code == 200, response.text
    parent_before = client.get(f"{ROOT}/{goal['id']}").json()
    assert parent_before == parent_complete
    before = client.get(milestone_url).json()

    response = client.post(f"{milestone_url}/status", json={"status": target})

    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["status"] == target
    if target == "COMPLETED":
        assert changed["completed_at"] is not None
        parsed = datetime.fromisoformat(changed["completed_at"].replace("Z", "+00:00"))
        assert parsed.utcoffset().total_seconds() == 0
        if initial == "COMPLETED":
            assert changed["completed_at"] == before["completed_at"]
    else:
        assert changed["completed_at"] is None
    assert client.get(f"{ROOT}/{goal['id']}").json() == parent_before


def test_milestone_recompletion_sets_fresh_utc_time_after_reopening(client):
    goal = create_goal(client)
    milestone = create_child(
        client, goal["id"], "milestones", {"title": "Recompletion"},
    )
    url = child_url(goal["id"], "milestones", milestone["id"])
    first = client.post(f"{url}/status", json={"status": "COMPLETED"}).json()
    repeated = client.post(f"{url}/status", json={"status": "COMPLETED"}).json()
    assert repeated["completed_at"] == first["completed_at"]
    reopened = client.post(f"{url}/status", json={"status": "IN_PROGRESS"}).json()
    assert reopened["completed_at"] is None
    final = client.post(f"{url}/status", json={"status": "COMPLETED"}).json()
    assert final["completed_at"] != first["completed_at"]
    assert datetime.fromisoformat(final["completed_at"].replace("Z", "+00:00")).utcoffset().total_seconds() == 0


@pytest.mark.parametrize("kind", ["items", "milestones", "checkpoints"])
def test_foreign_workspace_cannot_use_any_family_route_or_action(client, kind):
    goal = create_goal(client)
    record, update = child_setup(client, kind, goal["id"])
    url = child_url(goal["id"], kind, record["id"])
    with as_workspace("composition-other-workspace"):
        assert client.get(f"{ROOT}/{goal['id']}/composition").status_code == 404
        assert client.get(f"{ROOT}/{goal['id']}/{kind}").status_code == 404
        assert client.post(
            f"{ROOT}/{goal['id']}/{kind}",
            json={"name": "Foreign create"} if kind == "items"
            else {"title": "Foreign create"} if kind == "milestones"
            else {"amount": "1.00"},
        ).status_code == 404
        assert client.get(url).status_code == 404
        assert client.put(url, json=update).status_code == 404
        assert client.delete(url).status_code == 404
        if kind != "checkpoints":
            assert client.post(
                f"{url}/status", json={"status": wrong_child_status(kind)},
            ).status_code == 404
        if kind == "items":
            assert client.post(f"{url}/deactivate").status_code == 404
            assert client.post(f"{url}/reactivate").status_code == 404
    assert client.get(url).status_code == 200
    assert client.get(url).json() == record


@pytest.mark.parametrize("kind", ["items", "milestones", "checkpoints"])
def test_same_workspace_wrong_parent_record_ids_cannot_be_used(client, kind):
    parent = create_goal(client, name="Actual parent")
    other = create_goal(client, name="Different parent")
    record, update = child_setup(client, kind, parent["id"])
    wrong_url = child_url(other["id"], kind, record["id"])
    assert client.get(wrong_url).status_code == 404
    assert client.put(wrong_url, json=update).status_code == 404
    assert client.delete(wrong_url).status_code == 404
    if kind != "checkpoints":
        assert client.post(
            f"{wrong_url}/status", json={"status": wrong_child_status(kind)},
        ).status_code == 404
    if kind == "items":
        assert client.post(f"{wrong_url}/deactivate").status_code == 404
        assert client.post(f"{wrong_url}/reactivate").status_code == 404
    assert client.get(child_url(parent["id"], kind, record["id"])).json() == record


@pytest.mark.parametrize(("method", "url", "payload"), [
    ("GET", f"{ROOT}/composition/options", None),
    ("GET", f"{ROOT}/1/composition", None),
    ("GET", f"{ROOT}/1/items", None),
    ("POST", f"{ROOT}/1/items", {"name": "Unauthenticated"}),
    ("GET", f"{ROOT}/1/items/1", None),
    ("PUT", f"{ROOT}/1/items/1", {
        "name": "Unauthenticated", "description": None, "expected_cost": None,
        "manual_actual_cost_override": None, "notes": None, "sort_order": 0,
    }),
    ("DELETE", f"{ROOT}/1/items/1", None),
    ("POST", f"{ROOT}/1/items/1/status", {"status": "COMPLETED"}),
    ("POST", f"{ROOT}/1/items/1/deactivate", None),
    ("POST", f"{ROOT}/1/items/1/reactivate", None),
    ("GET", f"{ROOT}/1/milestones", None),
    ("POST", f"{ROOT}/1/milestones", {"title": "Unauthenticated"}),
    ("GET", f"{ROOT}/1/milestones/1", None),
    ("PUT", f"{ROOT}/1/milestones/1", {
        "title": "Unauthenticated", "description": None,
        "target_date": None, "sort_order": 0,
    }),
    ("DELETE", f"{ROOT}/1/milestones/1", None),
    ("POST", f"{ROOT}/1/milestones/1/status", {"status": "COMPLETED"}),
    ("GET", f"{ROOT}/1/checkpoints", None),
    ("POST", f"{ROOT}/1/checkpoints", {"amount": "0.00"}),
    ("GET", f"{ROOT}/1/checkpoints/1", None),
    ("PUT", f"{ROOT}/1/checkpoints/1", {
        "amount": "0.00", "label": None, "sort_order": 0,
    }),
    ("DELETE", f"{ROOT}/1/checkpoints/1", None),
])
def test_all_new_composition_routes_require_auth(real_auth_client, method, url, payload):
    assert real_auth_client.request(method, url, json=payload).status_code == 401


@pytest.mark.parametrize("kind", ["items", "milestones", "checkpoints"])
def test_inactive_parent_all_child_mutations_conflict_but_reads_stay_available(
    client, kind,
):
    goal = create_goal(client)
    record, update = child_setup(client, kind, goal["id"])
    url = child_url(goal["id"], kind, record["id"])
    assert client.post(f"{ROOT}/{goal['id']}/deactivate").status_code == 200

    assert client.get(f"{ROOT}/{goal['id']}/composition").status_code == 200
    assert client.get(f"{ROOT}/{goal['id']}/{kind}").status_code == 200
    assert client.get(url).status_code == 200
    create_payload = (
        {"name": "New"} if kind == "items" else
        {"title": "New"} if kind == "milestones" else {"amount": "1.00"}
    )
    assert client.post(f"{ROOT}/{goal['id']}/{kind}", json=create_payload).status_code == 409
    assert client.put(url, json=update).status_code == 409
    assert client.delete(url).status_code == 409
    if kind != "checkpoints":
        assert client.post(
            f"{url}/status", json={"status": wrong_child_status(kind)},
        ).status_code == 409
    if kind == "items":
        assert client.post(f"{url}/deactivate").status_code == 409
        assert client.post(f"{url}/reactivate").status_code == 409
    assert client.get(url).json() == record
    assert client.post(f"{ROOT}/{goal['id']}/reactivate").status_code == 200
    assert client.delete(url).status_code == 204
    assert client.delete(f"{ROOT}/{goal['id']}").status_code == 204


def test_maximum_item_costs_checkpoint_and_exact_zero_round_trip(client):
    assert "reached" not in Base.metadata.tables["goal_checkpoints"].c
    goal = create_goal(client, current_progress_amount="0.00")
    item = create_child(client, goal["id"], "items", {
        "name": "Maximum planning costs", "expected_cost": "1000000000000.00",
        "manual_actual_cost_override": "0.00",
    })
    assert item["expected_cost"] == "1000000000000.00"
    assert item["expected_cost_cents"] == 100_000_000_000_000
    assert item["manual_actual_cost_override"] == "0.00"
    assert item["manual_actual_cost_override_cents"] == 0
    update = {
        "name": "Maximum actual override", "description": None,
        "expected_cost": None, "manual_actual_cost_override": "1000000000000.00",
        "notes": None, "sort_order": 0,
    }
    saved = client.put(child_url(goal["id"], "items", item["id"]), json=update)
    assert saved.status_code == 200, saved.text
    assert saved.json()["expected_cost"] is None
    assert saved.json()["expected_cost_cents"] is None
    assert saved.json()["manual_actual_cost_override_cents"] == 100_000_000_000_000
    checkpoint = create_child(client, goal["id"], "checkpoints", {
        "amount": "1000000000000.00", "label": None,
    })
    assert checkpoint["amount_cents"] == 100_000_000_000_000
    assert checkpoint["amount"] == "1000000000000.00"
    zero = create_child(client, goal["id"], "checkpoints", {"amount": "0.00"})
    assert zero["amount_cents"] == 0
    assert zero["amount"] == "0.00"
    assert zero["reached"] is True


def test_legacy_reserved_source_with_nonnull_progress_keeps_checkpoint_unknown(
    client, db,
):
    goal = create_goal(client, current_progress_amount="50.00")
    checkpoint = create_child(client, goal["id"], "checkpoints", {"amount": "0.00"})
    row = db.get(Goal, goal["id"])
    row.progress_source = "PORTFOLIO_VALUE"
    db.commit()

    current = client.get(
        child_url(goal["id"], "checkpoints", checkpoint["id"]),
    )

    assert current.status_code == 200, current.text
    assert current.json()["reached"] is None
    assert current.json()["amount_cents"] == 0


def test_sqlite_immediate_parent_lock_serializes_child_write_before_parent_delete(
    tmp_path, client, monkeypatch,
):
    """Exercise the SQLite race with independent sessions against a private file DB."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from starlette.testclient import TestClient

    from auth import require_page_session

    path = tmp_path / "goal-composition-race.db"
    engine = create_engine(
        f"sqlite:///{path}", connect_args={"check_same_thread": False, "timeout": 10},
    )
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False)

    def database():
        with factory() as session:
            yield session

    old_db = app.dependency_overrides.get(get_db)
    old_owner = app.dependency_overrides.get(require_session)
    old_page_owner = app.dependency_overrides.get(require_page_session)
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_session] = lambda: "race-owner"
    app.dependency_overrides[require_page_session] = lambda: "race-owner"
    try:
        with TestClient(app) as race_client:
            goal = create_goal(race_client)
            holding_parent_lock = Event()
            delete_waiting_for_lock = Event()
            release_parent_lock = Event()
            writer_result = []
            deleter_result = []
            lock_attempts = [0]

            def pause_after_parent_lock(_connection, _cursor, statement, _params, _ctx, _many):
                normalized = statement.strip().lower()
                if normalized == "begin immediate":
                    lock_attempts[0] += 1
                    if lock_attempts[0] == 2:
                        delete_waiting_for_lock.set()
                if "from goals" in normalized and not holding_parent_lock.is_set():
                    holding_parent_lock.set()
                    assert release_parent_lock.wait(timeout=10)

            event.listen(engine, "before_cursor_execute", pause_after_parent_lock)

            def write_child():
                writer_result.append(race_client.post(
                    f"{ROOT}/{goal['id']}/items", json={"name": "Serialized child"},
                ))

            def delete_parent():
                deleter_result.append(race_client.delete(f"{ROOT}/{goal['id']}"))

            writer = Thread(target=write_child)
            deleter = Thread(target=delete_parent)
            writer.start()
            assert holding_parent_lock.wait(timeout=10)
            deleter.start()
            assert delete_waiting_for_lock.wait(timeout=10)
            release_parent_lock.set()
            writer.join(timeout=15)
            deleter.join(timeout=15)
            event.remove(engine, "before_cursor_execute", pause_after_parent_lock)

            assert not writer.is_alive()
            assert not deleter.is_alive()
            assert writer_result[0].status_code == 201, writer_result[0].text
            assert deleter_result[0].status_code == 409, deleter_result[0].text
            assert race_client.get(f"{ROOT}/{goal['id']}/items").status_code == 200
            assert len(race_client.get(f"{ROOT}/{goal['id']}/items").json()) == 1
            with engine.connect() as connection:
                # The private test connection uses SQLite's default setting;
                # application code must not globally enable foreign keys.
                assert connection.scalar(text("PRAGMA foreign_keys")) == 0
    finally:
        if old_db is None:
            app.dependency_overrides.pop(get_db, None)
        else:
            app.dependency_overrides[get_db] = old_db
        if old_owner is None:
            app.dependency_overrides.pop(require_session, None)
        else:
            app.dependency_overrides[require_session] = old_owner
        if old_page_owner is None:
            app.dependency_overrides.pop(require_page_session, None)
        else:
            app.dependency_overrides[require_page_session] = old_page_owner
        engine.dispose()