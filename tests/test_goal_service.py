"""Direct service ownership boundaries and Goal Core's financial independence."""

import pytest

from models.goal import Goal
from schemas.goal import GoalCreate, GoalUpdate
from services import goal_service
from services.ownership import MissingOwnerError

PAYLOAD = {"name": "Synthetic goal", "goal_type": "SAVINGS", "category": "FINANCIAL"}
OWNER = "synthetic-goal-workspace"


def _operations(db, goal_id, owner_id):
    return {
        "create": lambda: goal_service.create_goal(db, GoalCreate(**PAYLOAD), owner_id),
        "list": lambda: goal_service.list_goals(db, owner_id),
        "get": lambda: goal_service.get_goal(db, goal_id, owner_id),
        "update": lambda: goal_service.update_goal(db, goal_id, GoalUpdate(**PAYLOAD), owner_id),
        "archive": lambda: goal_service.set_goal_active(db, goal_id, False, owner_id),
        "reactivate": lambda: goal_service.set_goal_active(db, goal_id, True, owner_id),
        "status": lambda: goal_service.change_goal_status(db, goal_id, "COMPLETED", owner_id),
        "delete": lambda: goal_service.delete_goal(db, goal_id, owner_id),
    }


@pytest.mark.parametrize("owner_id", [None, "", "   ", "x" * 256])
@pytest.mark.parametrize("operation", [
    "create", "list", "get", "update", "archive", "reactivate", "status", "delete",
])
def test_every_goal_service_requires_a_valid_owner(db, owner_id, operation):
    goal = goal_service.create_goal(db, GoalCreate(**PAYLOAD), OWNER)
    with pytest.raises(MissingOwnerError):
        _operations(db, goal.id, owner_id)[operation]()
    unchanged = db.get(Goal, goal.id)
    assert unchanged.name == PAYLOAD["name"]
    assert unchanged.status == "NOT_STARTED"
    assert unchanged.active is True
    assert unchanged.completed_at is None


def test_direct_services_do_not_accept_a_foreign_owned_id(db):
    goal = goal_service.create_goal(db, GoalCreate(**PAYLOAD), OWNER)
    foreign = _operations(db, goal.id, "different-synthetic-workspace")
    assert foreign["list"]() == []
    assert foreign["get"]() is None
    for operation in ("update", "archive", "reactivate", "status", "delete"):
        with pytest.raises(goal_service.GoalNotFound, match="^Goal not found$"):
            foreign[operation]()
    assert db.get(Goal, goal.id).owner_id == OWNER
    assert db.get(Goal, goal.id).active is True
    assert db.get(Goal, goal.id).status == "NOT_STARTED"


def test_direct_status_service_rejects_invalid_status_without_mutation(db):
    goal = goal_service.create_goal(db, GoalCreate(**PAYLOAD), OWNER)
    with pytest.raises(ValueError, match="Status must be one of"):
        goal_service.change_goal_status(db, goal.id, "INVALID", OWNER)
    assert goal.status == "NOT_STARTED"
    assert goal.completed_at is None


@pytest.mark.parametrize(("method", "url", "payload"), [
    ("GET", "/serenity-api/goals/options", None),
    ("GET", "/serenity-api/goals", None),
    ("POST", "/serenity-api/goals", PAYLOAD),
    ("GET", "/serenity-api/goals/1", None),
    ("PUT", "/serenity-api/goals/1", PAYLOAD),
    ("DELETE", "/serenity-api/goals/1", None),
    ("POST", "/serenity-api/goals/1/deactivate", None),
    ("POST", "/serenity-api/goals/1/reactivate", None),
    ("POST", "/serenity-api/goals/1/status", {"status": "COMPLETED"}),
])
def test_all_goal_api_routes_require_sign_in(real_auth_client, method, url, payload):
    response = real_auth_client.request(method, url, json=payload)
    assert response.status_code == 401


def test_goals_page_keeps_the_existing_sign_in_gate(real_auth_client):
    response = real_auth_client.get("/goals", follow_redirects=False)
    assert response.status_code in (302, 303, 307)
    assert response.headers["location"].startswith("/sign-in")


def test_goal_lifecycle_does_not_change_financial_summary_or_existing_export_sections(client):
    account = client.post("/serenity-api/accounts", json={
        "name": "Synthetic cash", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "500.10",
    })
    debt = client.post("/serenity-api/debts", json={
        "name": "Synthetic debt", "debt_type": "Other", "balance": "125.25",
    })
    assert account.status_code == debt.status_code == 201
    before_dashboard = client.get("/serenity-api/dashboard/summary").json()
    before_finance = client.get("/serenity-api/finance/summary").json()
    before_export = client.get("/serenity-api/export").json()

    invalid_goal = client.post("/serenity-api/goals", json={
        **PAYLOAD, "goal_type": "INVESTMENT", "progress_source": "PORTFOLIO_VALUE",
        "target_amount": "999999999999.99", "current_progress_amount": "100.01",
    })
    assert invalid_goal.status_code == 422
    assert "Current progress amount can only be set when progress source is MANUAL." in invalid_goal.text
    assert client.get("/serenity-api/goals").json() == []
    assert client.get("/serenity-api/dashboard/summary").json() == before_dashboard
    assert client.get("/serenity-api/finance/summary").json() == before_finance

    goal = client.post("/serenity-api/goals", json={
        **PAYLOAD, "goal_type": "INVESTMENT", "progress_source": "PORTFOLIO_VALUE",
        "target_amount": "999999999999.99", "current_progress_amount": None,
    })
    assert goal.status_code == 201
    goal_id = goal.json()["id"]
    for action, payload in (("status", {"status": "COMPLETED"}),
                            ("deactivate", None), ("reactivate", None)):
        assert client.post(f"/serenity-api/goals/{goal_id}/{action}", json=payload).status_code == 200
    assert client.get("/serenity-api/dashboard/summary").json() == before_dashboard
    assert client.get("/serenity-api/finance/summary").json() == before_finance
    after_export = client.get("/serenity-api/export").json()
    for key, value in before_export.items():
        if key not in ("goals", "exported_at"):
            assert after_export[key] == value, f"Goal Core changed existing export section {key}"
    assert client.delete(f"/serenity-api/goals/{goal_id}").status_code == 204
    assert client.get("/serenity-api/dashboard/summary").json() == before_dashboard