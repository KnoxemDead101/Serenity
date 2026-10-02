"""Goal Composition API, ownership, lifecycle, and derived progress coverage."""

from contextlib import contextmanager
from datetime import datetime

import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from auth import require_session
from main import app
from schemas.goal import GoalCreate
from schemas.goal_composition import (
    GoalCheckpointCreate, GoalCheckpointUpdate, GoalItemCreate, GoalItemUpdate,
    GoalMilestoneCreate, GoalMilestoneUpdate,
)
from services import goal_composition_service
from services import goal_service
from services.ownership import MissingOwnerError
from storage.database import Base


ROOT = "/serenity-api/goals"
GOAL = {
    "name": "Composition test goal",
    "goal_type": "SAVINGS",
    "category": "FINANCIAL",
    "target_amount": "500.00",
    "current_progress_amount": "250.00",
    "progress_source": "MANUAL",
}


def _create_goal(client, **changes):
    response = client.post(ROOT, json={**GOAL, **changes})
    assert response.status_code == 201, response.text
    return response.json()


def _create(client, goal_id, kind, payload):
    response = client.post(f"{ROOT}/{goal_id}/{kind}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


@contextmanager
def _as_workspace(owner_id):
    previous = app.dependency_overrides.get(require_session)
    app.dependency_overrides[require_session] = lambda: owner_id
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(require_session, None)
        else:
            app.dependency_overrides[require_session] = previous


def test_composition_options_and_detail_have_canonical_statuses_and_sorted_children(client):
    options = client.get(f"{ROOT}/composition/options")
    assert options.status_code == 200, options.text
    assert options.json() == {
        "item_statuses": [
            "PLANNED", "IN_PROGRESS", "COMPLETED", "SKIPPED", "CANCELLED",
        ],
        "milestone_statuses": [
            "NOT_STARTED", "IN_PROGRESS", "COMPLETED", "SKIPPED", "CANCELLED",
        ],
    }
    goal = _create_goal(client)
    item_late = _create(client, goal["id"], "items", {
        "name": "Later item", "expected_cost": "12.34", "sort_order": 4,
    })
    item_early = _create(client, goal["id"], "items", {
        "name": "Earlier item", "expected_cost": None, "sort_order": 1,
    })
    milestone = _create(client, goal["id"], "milestones", {
        "title": "First milestone", "target_date": "2027-01-02",
        "sort_order": 0,
    })
    checkpoint = _create(client, goal["id"], "checkpoints", {
        "amount": "250.00", "label": "Halfway", "sort_order": 2,
    })

    response = client.get(f"{ROOT}/{goal['id']}/composition")
    assert response.status_code == 200, response.text
    composition = response.json()
    assert composition["goal"]["id"] == goal["id"]
    assert [row["id"] for row in composition["items"]] == [
        item_early["id"], item_late["id"],
    ]
    assert composition["items"][1]["expected_cost_cents"] == 1234
    assert composition["items"][1]["expected_cost"] == "12.34"
    assert composition["items"][0]["status"] == "PLANNED"
    assert composition["items"][0]["active"] is True
    assert composition["milestones"][0]["id"] == milestone["id"]
    assert composition["milestones"][0]["status"] == "NOT_STARTED"
    assert composition["milestones"][0]["target_date"] == "2027-01-02"
    assert composition["checkpoints"][0]["id"] == checkpoint["id"]
    assert composition["checkpoints"][0]["amount_cents"] == 25000
    assert composition["checkpoints"][0]["amount"] == "250.00"
    assert composition["checkpoints"][0]["reached"] is True
    assert all("owner_id" not in row for field in ("items", "milestones", "checkpoints")
               for row in composition[field])


@pytest.mark.parametrize(("kind", "payload"), [
    ("items", {"name": "Invalid", "status": "NOT_A_STATUS"}),
    ("items", {"name": "Invalid", "status": "COMPLETED"}),
    ("items", {"name": "Invalid", "owner_id": "injected"}),
    ("items", {"name": "Invalid", "goal_id": 999}),
    ("items", {"name": "Invalid", "completed_at": None}),
    ("milestones", {"title": "Invalid", "status": "PLANNED"}),
    ("milestones", {"title": "Invalid", "owner_id": "injected"}),
    ("milestones", {"title": "Invalid", "goal_id": 999}),
    ("milestones", {"title": "Invalid", "completed_at": "2026-10-01T00:00:00Z"}),
    ("checkpoints", {"amount": "1.005"}),
    ("checkpoints", {"amount": "-0.01"}),
    ("checkpoints", {"amount": "1000000000000.01"}),
    ("checkpoints", {"amount": "0.00", "reached": True}),
    ("checkpoints", {"amount": "0.00", "owner_id": "injected"}),
    ("checkpoints", {"amount": "0.00", "goal_id": 999}),
])
def test_child_create_rejects_invalid_money_status_and_protected_fields(
    client, kind, payload,
):
    goal = _create_goal(client)
    response = client.post(f"{ROOT}/{goal['id']}/{kind}", json=payload)
    assert response.status_code == 422, response.text
    assert client.get(f"{ROOT}/{goal['id']}/{kind}").json() == []


@pytest.mark.parametrize("sort_order", ["1", 1.0, True, -1, 2_147_483_648])
def test_child_sort_order_requires_a_bounded_strict_nonnegative_integer(
    client, sort_order,
):
    goal = _create_goal(client)
    response = client.post(f"{ROOT}/{goal['id']}/items", json={
        "name": "Invalid order", "sort_order": sort_order,
    })
    assert response.status_code == 422
    assert client.get(f"{ROOT}/{goal['id']}/items").json() == []


@pytest.mark.parametrize("field,value", [
    ("expected_cost", "-0.01"),
    ("expected_cost", "1.005"),
    ("expected_cost", "1000000000000.01"),
    ("expected_cost", "NaN"),
    ("manual_actual_cost_override", "-0.01"),
    ("manual_actual_cost_override", "1.005"),
    ("manual_actual_cost_override", "1000000000000.01"),
    ("manual_actual_cost_override", "Infinity"),
])
def test_item_cost_inputs_are_exact_nonnegative_bounded_money(client, field, value):
    goal = _create_goal(client)
    response = client.post(f"{ROOT}/{goal['id']}/items", json={
        "name": "Invalid cost", field: value,
    })
    assert response.status_code == 422
    assert client.get(f"{ROOT}/{goal['id']}/items").json() == []


def test_composition_export_is_nested_scoped_sorted_and_derived_fields_are_omitted(client):
    goal = _create_goal(client)
    late = _create(client, goal["id"], "items", {
        "name": "Late", "sort_order": 5,
    })
    early = _create(client, goal["id"], "items", {
        "name": "Early", "sort_order": 1,
    })
    assert client.post(
        f"{ROOT}/{goal['id']}/items/{early['id']}/deactivate"
    ).status_code == 200
    _create(client, goal["id"], "milestones", {"title": "Deliver"})
    _create(client, goal["id"], "checkpoints", {"amount": "250.00"})

    exported = client.get("/serenity-api/export")
    assert exported.status_code == 200, exported.text
    backup = exported.json()
    assert backup["format_version"] == 7
    record = next(row for row in backup["goals"] if row["id"] == goal["id"])
    assert [row["id"] for row in record["items"]] == [early["id"], late["id"]]
    assert record["items"][0]["active"] is False
    assert len(record["milestones"]) == len(record["checkpoints"]) == 1
    assert "reached" not in record["checkpoints"][0]
    with _as_workspace("composition-export-foreign"):
        other = client.get("/serenity-api/export")
    assert other.status_code == 200
    assert other.json()["goals"] == []


def test_composition_writes_do_not_change_financial_activity_or_transaction_csv(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Composition invariant account", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "599.00",
    })
    assert account.status_code == 201, account.text
    before = {
        "dashboard": client.get("/serenity-api/dashboard/summary").json(),
        "finance": client.get("/serenity-api/finance/summary").json(),
        "accounts": client.get("/serenity-api/accounts").json(),
        "debts": client.get("/serenity-api/debts").json(),
        "transactions": client.get(
            f"/serenity-api/accounts/{account.json()['id']}/transactions"
        ).json(),
        "portfolios": client.get("/serenity-api/portfolios").json(),
        "investments": client.get("/serenity-api/investments").json(),
        "income": client.get("/serenity-api/income-profiles").json(),
        "csv": client.get("/serenity-api/export/transactions.csv").content,
    }
    goal = _create_goal(client, current_progress_amount="599.00")
    parent_before_composition = client.get(f"{ROOT}/{goal['id']}").json()
    item = _create(client, goal["id"], "items", {
        "name": "Plan", "expected_cost": "599.00",
        "manual_actual_cost_override": "599.00",
    })
    _create(client, goal["id"], "checkpoints", {"amount": "500.00"})
    milestone = _create(client, goal["id"], "milestones", {"title": "Complete"})
    completed = client.post(
        f"{ROOT}/{goal['id']}/milestones/{milestone['id']}/status",
        json={"status": "COMPLETED"},
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    assert completed.json()["completed_at"] is not None
    assert client.get(f"{ROOT}/{goal['id']}").json() == parent_before_composition
    current = {
        "dashboard": client.get("/serenity-api/dashboard/summary").json(),
        "finance": client.get("/serenity-api/finance/summary").json(),
        "accounts": client.get("/serenity-api/accounts").json(),
        "debts": client.get("/serenity-api/debts").json(),
        "transactions": client.get(
            f"/serenity-api/accounts/{account.json()['id']}/transactions"
        ).json(),
        "portfolios": client.get("/serenity-api/portfolios").json(),
        "investments": client.get("/serenity-api/investments").json(),
        "income": client.get("/serenity-api/income-profiles").json(),
        "csv": client.get("/serenity-api/export/transactions.csv").content,
    }
    assert current == before
    assert item["expected_cost_cents"] == item["manual_actual_cost_override_cents"] == 59900
    assert client.get(
        f"{ROOT}/{goal['id']}/checkpoints"
    ).json()[0]["reached"] is True


def test_goal_detail_uses_fixed_four_selects_and_goal_list_loads_no_children(client, db):
    goal = _create_goal(client)
    for index in range(3):
        _create(client, goal["id"], "items", {"name": f"Item {index}"})
        _create(client, goal["id"], "milestones", {"title": f"Milestone {index}"})
        _create(client, goal["id"], "checkpoints", {"amount": f"{index}.00"})
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        detail = client.get(f"{ROOT}/{goal['id']}/composition")
        detail_count = len(statements)
        statements.clear()
        listing = client.get(ROOT)
        list_statements = list(statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)

    assert detail.status_code == 200, detail.text
    assert detail_count == 4
    assert len(detail.json()["items"]) == 3
    assert listing.status_code == 200, listing.text
    assert not any(
        table in statement
        for statement in list_statements
        for table in ("goal_items", "goal_milestones", "goal_checkpoints")
    )


def test_composition_export_child_query_count_is_constant_as_goal_count_grows(client, db):
    first = _create_goal(client)
    _create(client, first["id"], "items", {"name": "First item"})
    statements = []

    def capture(_conn, _cursor, statement, _parameters, _context, _executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            statements.append(statement.lower())

    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        first_export = client.get("/serenity-api/export")
        first_count = len(statements)
        statements.clear()
        for index in range(4):
            goal = _create_goal(client, name=f"Additional goal {index}")
            _create(client, goal["id"], "items", {"name": f"Item {index}"})
            _create(client, goal["id"], "milestones", {"title": f"Milestone {index}"})
            _create(client, goal["id"], "checkpoints", {"amount": f"{index + 1}.00"})
        statements.clear()
        second_export = client.get("/serenity-api/export")
        second_count = len(statements)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert first_export.status_code == second_export.status_code == 200
    assert first_count == second_count


def test_child_crud_full_put_status_and_item_archive_are_independent(client):
    goal = _create_goal(client)
    item = _create(client, goal["id"], "items", {
        "name": "Initial item", "expected_cost": "20.00",
    })
    item_url = f"{ROOT}/{goal['id']}/items/{item['id']}"
    changed = client.put(item_url, json={
        "name": "Revised item", "description": None, "expected_cost": "0.00",
        "manual_actual_cost_override": "15.50", "notes": "Reviewed",
        "sort_order": 9,
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["name"] == "Revised item"
    assert changed.json()["expected_cost_cents"] == 0
    assert changed.json()["manual_actual_cost_override_cents"] == 1550
    assert changed.json()["notes"] == "Reviewed"

    for status in ("IN_PROGRESS", "COMPLETED", "SKIPPED", "CANCELLED", "PLANNED"):
        result = client.post(f"{item_url}/status", json={"status": status})
        assert result.status_code == 200, result.text
        assert result.json()["status"] == status
        assert "completed_at" not in result.json()
        assert client.get(f"{ROOT}/{goal['id']}").json()["status"] == "NOT_STARTED"
    archived = client.post(f"{item_url}/deactivate")
    assert archived.status_code == 200, archived.text
    assert archived.json()["active"] is False
    assert archived.json()["status"] == "PLANNED"
    assert client.get(f"{ROOT}/{goal['id']}/composition").json()["items"] == []
    assert len(client.get(
        f"{ROOT}/{goal['id']}/composition?active_only=false"
    ).json()["items"]) == 1
    edited_archived = client.put(item_url, json={
        "name": "Edited while archived", "description": None,
        "expected_cost": None, "manual_actual_cost_override": None,
        "notes": None, "sort_order": 0,
    })
    assert edited_archived.status_code == 200, edited_archived.text
    assert edited_archived.json()["active"] is False
    restored = client.post(f"{item_url}/reactivate")
    assert restored.status_code == 200, restored.text
    assert restored.json()["active"] is True

    milestone = _create(client, goal["id"], "milestones", {
        "title": "Deliver", "target_date": None,
    })
    milestone_url = f"{ROOT}/{goal['id']}/milestones/{milestone['id']}"
    changed_milestone = client.put(milestone_url, json={
        "title": "Deliver revised", "description": "A date-bound goal",
        "target_date": "2028-02-29", "sort_order": 3,
    })
    assert changed_milestone.status_code == 200, changed_milestone.text
    assert changed_milestone.json()["target_date"] == "2028-02-29"
    completed = client.post(
        f"{milestone_url}/status", json={"status": "COMPLETED"},
    )
    assert completed.status_code == 200, completed.text
    timestamp = completed.json()["completed_at"]
    assert timestamp is not None
    assert datetime.fromisoformat(timestamp.replace("Z", "+00:00")).utcoffset().total_seconds() == 0
    repeated = client.post(
        f"{milestone_url}/status", json={"status": "COMPLETED"},
    )
    assert repeated.json()["completed_at"] == timestamp
    reopened = client.post(
        f"{milestone_url}/status", json={"status": "IN_PROGRESS"},
    )
    assert reopened.json()["completed_at"] is None
    completed_again = client.post(
        f"{milestone_url}/status", json={"status": "COMPLETED"},
    )
    assert completed_again.json()["completed_at"] != timestamp

    checkpoint = _create(client, goal["id"], "checkpoints", {
        "amount": "25.00", "label": None,
    })
    checkpoint_url = f"{ROOT}/{goal['id']}/checkpoints/{checkpoint['id']}"
    revised_checkpoint = client.put(checkpoint_url, json={
        "amount": "250.00", "label": "Updated threshold", "sort_order": 5,
    })
    assert revised_checkpoint.status_code == 200, revised_checkpoint.text
    assert revised_checkpoint.json()["amount_cents"] == 25000
    assert revised_checkpoint.json()["reached"] is True
    assert client.delete(checkpoint_url).status_code == 204
    assert client.delete(milestone_url).status_code == 204
    assert client.delete(item_url).status_code == 204
    assert client.delete(f"{ROOT}/{goal['id']}").status_code == 204


def test_checkpoint_reached_is_derived_from_fresh_manual_progress(client):
    goal = _create_goal(client, current_progress_amount="0.00")
    zero = _create(client, goal["id"], "checkpoints", {"amount": "0.00"})
    threshold = _create(client, goal["id"], "checkpoints", {"amount": "1.00"})
    assert zero["reached"] is True
    assert threshold["reached"] is False
    assert "reached" not in threshold or threshold["reached"] is False
    response = client.put(f"{ROOT}/{goal['id']}", json={
        **GOAL, "current_progress_amount": "1.00",
    })
    assert response.status_code == 200, response.text
    composition = client.get(f"{ROOT}/{goal['id']}/composition").json()
    reached = {row["id"]: row["reached"] for row in composition["checkpoints"]}
    assert reached[threshold["id"]] is True
    assert reached[zero["id"]] is True
    response = client.put(f"{ROOT}/{goal['id']}", json={
        **GOAL, "current_progress_amount": "0.50",
    })
    assert response.status_code == 200, response.text
    composition = client.get(f"{ROOT}/{goal['id']}/composition").json()
    reached = {row["id"]: row["reached"] for row in composition["checkpoints"]}
    assert reached[threshold["id"]] is False
    assert reached[zero["id"]] is True
    assert client.put(f"{ROOT}/{goal['id']}", json={
        **GOAL, "progress_source": "ACCOUNT_BALANCE",
        "current_progress_amount": None,
    }).status_code == 200
    composition = client.get(f"{ROOT}/{goal['id']}/composition").json()
    assert all(row["reached"] is None for row in composition["checkpoints"])


def test_parent_delete_blocked_and_inactive_parent_read_only(client):
    goal = _create_goal(client)
    item = _create(client, goal["id"], "items", {"name": "Archive me"})
    item_url = f"{ROOT}/{goal['id']}/items/{item['id']}"
    assert client.post(f"{item_url}/deactivate").status_code == 200
    assert client.delete(f"{ROOT}/{goal['id']}").status_code == 409
    assert client.post(f"{ROOT}/{goal['id']}/deactivate").status_code == 200

    assert client.get(f"{ROOT}/{goal['id']}/composition").status_code == 200
    assert client.get(item_url).status_code == 200
    assert client.get(f"{ROOT}/{goal['id']}/items").status_code == 200
    assert client.put(item_url, json={
        "name": "No edit", "description": None, "expected_cost": None,
        "manual_actual_cost_override": None, "notes": None, "sort_order": 0,
    }).status_code == 409
    assert client.post(f"{ROOT}/{goal['id']}/items", json={
        "name": "No create",
    }).status_code == 409
    assert client.post(f"{item_url}/reactivate").status_code == 409
    assert client.post(f"{item_url}/status", json={"status": "COMPLETED"}).status_code == 409
    assert client.delete(item_url).status_code == 409

    assert client.post(f"{ROOT}/{goal['id']}/reactivate").status_code == 200
    assert client.delete(item_url).status_code == 204
    assert client.delete(f"{ROOT}/{goal['id']}").status_code == 204


def test_nested_routes_cannot_access_foreign_goal_or_child_ids(client):
    first = _create_goal(client, name="First")
    second = _create_goal(client, name="Second")
    own_item = _create(client, first["id"], "items", {"name": "Private"})
    other_item = _create(client, second["id"], "items", {"name": "Other"})
    own_path = f"{ROOT}/{first['id']}/items/{own_item['id']}"
    wrong_parent_path = f"{ROOT}/{second['id']}/items/{own_item['id']}"

    with _as_workspace("other-composition-workspace"):
        assert client.get(f"{ROOT}/{first['id']}/composition").status_code == 404
        assert client.get(f"{ROOT}/{first['id']}/items").status_code == 404
        assert client.get(own_path).status_code == 404
        assert client.put(own_path, json={
            "name": "Foreign edit", "description": None, "expected_cost": None,
            "manual_actual_cost_override": None, "notes": None, "sort_order": 0,
        }).status_code == 404
        assert client.post(f"{own_path}/deactivate").status_code == 404
        assert client.delete(own_path).status_code == 404

    assert client.get(wrong_parent_path).status_code == 404
    assert client.get(f"{ROOT}/{first['id']}/items/{other_item['id']}").status_code == 404
    assert client.get(own_path).json()["name"] == "Private"


@pytest.mark.parametrize("table_name,fields", [
    ("goal_items", {"name": "Valid child", "status": "PLANNED", "active": True}),
    ("goal_milestones", {"title": "Valid milestone", "status": "NOT_STARTED"}),
    ("goal_checkpoints", {"amount_cents": 0}),
])
@pytest.mark.parametrize("broken_field", ["owner_id", "goal_id"])
def test_sqlite_composite_child_foreign_keys_with_private_foreign_keys_on(
    table_name, fields, broken_field,
):
    """Enable SQLite FK checks only on this isolated test-owned engine."""
    engine = create_engine("sqlite://")

    @event.listens_for(engine, "connect")
    def enable_private_foreign_keys(connection, _record):
        connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine, autoflush=False)
    try:
        with factory() as db:
            goal = goal_service.create_goal(
                db,
                GoalCreate(name="FK parent", goal_type="SAVINGS", category="FINANCIAL"),
                "sqlite-composition-owner",
            )
            table = Base.metadata.tables[table_name]
            with pytest.raises(IntegrityError):
                db.execute(table.insert().values(
                    owner_id="foreign-owner", goal_id=goal.id, **fields,
                ))
            db.rollback()

            child = db.execute(table.insert().values(
                owner_id="sqlite-composition-owner", goal_id=goal.id, **fields,
            ))
            db.commit()
            child_id = child.inserted_primary_key[0]
            bad_value = "foreign-owner" if broken_field == "owner_id" else goal.id + 1
            with pytest.raises(IntegrityError):
                db.execute(
                    table.update().where(table.c.id == child_id).values(
                        **{broken_field: bad_value},
                    )
                )
            db.rollback()
    finally:
        engine.dispose()


@pytest.mark.parametrize("owner_id", [None, "", "   ", "x" * 256])
@pytest.mark.parametrize("operation", [
    "list_items", "get_item", "create_item", "update_item", "delete_item",
    "change_item_status", "set_item_active", "list_milestones",
    "get_milestone", "create_milestone", "update_milestone",
    "delete_milestone", "change_milestone_status", "list_checkpoints",
    "get_checkpoint", "create_checkpoint", "update_checkpoint",
    "delete_checkpoint", "get_composition",
])
def test_every_composition_service_requires_a_valid_owner(db, owner_id, operation):
    goal = goal_service.create_goal(
        db, GoalCreate(name="Direct-service goal", goal_type="SAVINGS",
                       category="FINANCIAL"), "direct-service-owner",
    )
    item = goal_composition_service.create_goal_item(
        db, goal.id, GoalItemCreate(name="Direct item"), "direct-service-owner",
    )
    milestone = goal_composition_service.create_goal_milestone(
        db, goal.id, GoalMilestoneCreate(title="Direct milestone"),
        "direct-service-owner",
    )
    checkpoint = goal_composition_service.create_goal_checkpoint(
        db, goal.id, GoalCheckpointCreate(amount="0.00"),
        "direct-service-owner",
    )
    operations = {
        "list_items": lambda: goal_composition_service.list_goal_items(db, goal.id, owner_id),
        "get_item": lambda: goal_composition_service.get_goal_item(db, goal.id, item.id, owner_id),
        "create_item": lambda: goal_composition_service.create_goal_item(
            db, goal.id, GoalItemCreate(name="Attempt"), owner_id,
        ),
        "update_item": lambda: goal_composition_service.update_goal_item(
            db, goal.id, item.id, GoalItemUpdate(
                name="Attempt", description=None, expected_cost=None,
                manual_actual_cost_override=None, notes=None, sort_order=0,
            ), owner_id,
        ),
        "delete_item": lambda: goal_composition_service.delete_goal_item(
            db, goal.id, item.id, owner_id,
        ),
        "change_item_status": lambda: goal_composition_service.change_goal_item_status(
            db, goal.id, item.id, "COMPLETED", owner_id,
        ),
        "set_item_active": lambda: goal_composition_service.set_goal_item_active(
            db, goal.id, item.id, False, owner_id,
        ),
        "list_milestones": lambda: goal_composition_service.list_goal_milestones(
            db, goal.id, owner_id,
        ),
        "get_milestone": lambda: goal_composition_service.get_goal_milestone(
            db, goal.id, milestone.id, owner_id,
        ),
        "create_milestone": lambda: goal_composition_service.create_goal_milestone(
            db, goal.id, GoalMilestoneCreate(title="Attempt"), owner_id,
        ),
        "update_milestone": lambda: goal_composition_service.update_goal_milestone(
            db, goal.id, milestone.id, GoalMilestoneUpdate(
                title="Attempt", description=None, target_date=None, sort_order=0,
            ), owner_id,
        ),
        "delete_milestone": lambda: goal_composition_service.delete_goal_milestone(
            db, goal.id, milestone.id, owner_id,
        ),
        "change_milestone_status": lambda: goal_composition_service.change_goal_milestone_status(
            db, goal.id, milestone.id, "COMPLETED", owner_id,
        ),
        "list_checkpoints": lambda: goal_composition_service.list_goal_checkpoints(
            db, goal.id, owner_id,
        ),
        "get_checkpoint": lambda: goal_composition_service.get_goal_checkpoint(
            db, goal.id, checkpoint.id, owner_id,
        ),
        "create_checkpoint": lambda: goal_composition_service.create_goal_checkpoint(
            db, goal.id, GoalCheckpointCreate(amount="1.00"), owner_id,
        ),
        "update_checkpoint": lambda: goal_composition_service.update_goal_checkpoint(
            db, goal.id, checkpoint.id, GoalCheckpointUpdate(
                amount="1.00", label=None, sort_order=0,
            ), owner_id,
        ),
        "delete_checkpoint": lambda: goal_composition_service.delete_goal_checkpoint(
            db, goal.id, checkpoint.id, owner_id,
        ),
        "get_composition": lambda: goal_composition_service.get_goal_composition(
            db, goal.id, owner_id,
        ),
    }

    with pytest.raises(MissingOwnerError):
        operations[operation]()
    assert len(goal_composition_service.list_goal_items(
        db, goal.id, "direct-service-owner",
    )) == 1
    assert len(goal_composition_service.list_goal_milestones(
        db, goal.id, "direct-service-owner",
    )) == 1
    assert len(goal_composition_service.list_goal_checkpoints(
        db, goal.id, "direct-service-owner",
    )) == 1