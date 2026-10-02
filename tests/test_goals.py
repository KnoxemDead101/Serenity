"""Goal Core API tests: validation, workspace ownership, lifecycle and export."""

from contextlib import contextmanager
from datetime import datetime

import pytest
from pydantic import ValidationError

from auth import require_session
from conftest import TEST_OWNER_ID
from main import app
from schemas.goal import GoalCreate


ROOT = "/serenity-api/goals"
VALID_GOAL = {
    "name": "Emergency reserve",
    "description": "Build a cash reserve",
    "goal_type": "SAVINGS",
    "category": "FINANCIAL",
    "target_date": "2027-12-31",
    "target_amount": "25000.00",
    "current_progress_amount": "125.50",
    "progress_source": "MANUAL",
    "notes": "Reviewed quarterly",
}
GOAL_TYPES = [
    "SAVINGS", "DEBT_REDUCTION", "PURCHASE", "SPENDING_BUDGET",
    "INVESTMENT", "INCOME", "GENERAL_FINANCIAL", "NONFINANCIAL",
]
GOAL_CATEGORIES = [
    "FINANCIAL", "CAREER", "BUSINESS", "FAMILY",
    "INVESTING", "TRADING", "OTHER",
]
GOAL_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "PAUSED", "CANCELLED"]
GOAL_PRIORITIES = ["HIGH", "NORMAL", "LOW"]
GOAL_PROGRESS_SOURCES = [
    "MANUAL", "TRANSACTION_ACTIVITY", "ACCOUNT_BALANCE", "DEBT_BALANCE",
    "PORTFOLIO_VALUE", "INVESTMENT_ACCOUNT", "BUSINESS_METRIC", "MILESTONES",
]


def create_goal(client, **changes):
    response = client.post(ROOT, json={**VALID_GOAL, **changes})
    assert response.status_code == 201, response.text
    return response.json()


@contextmanager
def as_workspace(owner_id):
    """Run one test client request as a different synthetic workspace."""
    previous = app.dependency_overrides.get(require_session)
    app.dependency_overrides[require_session] = lambda: owner_id
    try:
        yield
    finally:
        if previous is None:
            app.dependency_overrides.pop(require_session, None)
        else:
            app.dependency_overrides[require_session] = previous


def test_goal_choices_endpoint_exposes_the_canonical_core_options(client):
    options = client.get(ROOT + "/options")
    assert options.status_code == 200
    assert options.json() == {
        "goal_types": GOAL_TYPES,
        "categories": GOAL_CATEGORIES,
        "statuses": GOAL_STATUSES,
        "priorities": GOAL_PRIORITIES,
        "progress_sources": GOAL_PROGRESS_SOURCES,
    }


@pytest.mark.parametrize(("goal_type", "category"), [
    ("SAVINGS", "FINANCIAL"),
    ("DEBT_REDUCTION", "FINANCIAL"),
    ("PURCHASE", "FAMILY"),
    ("INVESTMENT", "INVESTING"),
    ("INCOME", "BUSINESS"),
    ("GENERAL_FINANCIAL", "TRADING"),
    ("NONFINANCIAL", "CAREER"),
    ("NONFINANCIAL", "OTHER"),
])
def test_create_financial_and_nonfinancial_goals(
    client, goal_type, category,
):
    goal = create_goal(
        client, goal_type=goal_type, category=category,
        description="  Work toward the plan  ",
    )

    assert goal["name"] == "Emergency reserve"
    assert goal["description"] == "Work toward the plan"
    assert goal["goal_type"] == goal_type
    assert goal["category"] == category
    assert goal["status"] == "NOT_STARTED"
    assert goal["priority"] == "NORMAL"
    assert goal["progress_source"] == "MANUAL"
    assert goal["target_amount"] == "25000.00"
    assert goal["target_amount_cents"] == 2_500_000
    assert goal["current_progress_amount"] == "125.50"
    assert goal["current_progress_amount_cents"] == 12_550
    assert goal["target_date"] == "2027-12-31"
    assert goal["active"] is True
    assert goal["completed_at"] is None
    assert "owner_id" not in goal
    assert goal["created_at"].startswith("20")
    assert goal["updated_at"].startswith("20")


def test_goal_without_target_date_or_amount_uses_exact_nulls(client):
    goal = create_goal(
        client,
        name="Keep learning",
        goal_type="NONFINANCIAL",
        category="CAREER",
        target_date=None,
        target_amount=None,
        current_progress_amount=None,
    )

    assert goal["target_date"] is None
    assert goal["target_amount"] is None
    assert goal["target_amount_cents"] is None
    assert goal["current_progress_amount"] is None
    assert goal["current_progress_amount_cents"] is None


def test_goal_can_store_a_very_large_exact_cent_amount(client):
    goal = create_goal(
        client,
        target_amount="1000000000000.00",
        current_progress_amount="999999999999.99",
    )

    assert goal["target_amount"] == "1000000000000.00"
    assert goal["target_amount_cents"] == 100_000_000_000_000
    assert goal["current_progress_amount"] == "999999999999.99"
    assert goal["current_progress_amount_cents"] == 99_999_999_999_999


@pytest.mark.parametrize(("initial", "target"), [
    (initial, target)
    for initial in GOAL_STATUSES
    for target in GOAL_STATUSES
])
def test_every_goal_status_transition_sets_and_clears_completion_at_correctly(
    client, initial, target,
):
    created = create_goal(client)
    if initial != "NOT_STARTED":
        transition = client.post(
            f"{ROOT}/{created['id']}/status", json={"status": initial}
        )
        assert transition.status_code == 200, transition.text
        created = transition.json()
    assert created["status"] == initial
    original_completed_at = created["completed_at"]
    assert (original_completed_at is not None) is (initial == "COMPLETED")

    response = client.post(f"{ROOT}/{created['id']}/status", json={"status": target})

    assert response.status_code == 200, response.text
    goal = response.json()
    assert goal["status"] == target
    if target == "COMPLETED":
        assert goal["completed_at"] is not None
        completed = datetime.fromisoformat(goal["completed_at"].replace("Z", "+00:00"))
        assert completed.utcoffset().total_seconds() == 0
        if initial == "COMPLETED":
            assert goal["completed_at"] == original_completed_at
    else:
        assert goal["completed_at"] is None


def test_moving_out_of_completed_and_back_clears_and_sets_a_fresh_timestamp(client):
    goal = create_goal(client)
    completed = client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": "COMPLETED"}
    ).json()["completed_at"]
    assert completed is not None

    paused = client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": "PAUSED"}
    ).json()
    assert paused["completed_at"] is None

    again = client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": "COMPLETED"}
    ).json()
    assert again["completed_at"] is not None
    assert again["completed_at"] != completed


@pytest.mark.parametrize(("field", "value"), [
    ("goal_type", "NOT_A_GOAL_TYPE"),
    ("category", "NOT_A_CATEGORY"),
    ("status", "FINISHED"),
    ("priority", "URGENT"),
    ("progress_source", "AUTOMATIC"),
])
def test_create_rejects_every_invalid_goal_choice(client, field, value):
    response = client.post(ROOT, json={**VALID_GOAL, field: value})

    assert response.status_code == 422
    assert client.get(ROOT).json() == []


@pytest.mark.parametrize("status", GOAL_STATUSES + ["UNKNOWN"])
def test_create_schema_rejects_status_as_protected_input(status):
    with pytest.raises(ValidationError):
        GoalCreate(**VALID_GOAL, status=status)


def test_create_rejects_valid_status_injection_in_http_request(client):
    response = client.post(
        ROOT, json={**VALID_GOAL, "status": "COMPLETED"}
    )

    assert response.status_code == 422
    assert client.get(ROOT).json() == []


@pytest.mark.parametrize(("field", "value"), [
    ("goal_type", "INVALID_TYPE"),
    ("category", "INVALID_CATEGORY"),
    ("priority", "INVALID_PRIORITY"),
    ("progress_source", "AUTOMATIC"),
])
def test_update_rejects_each_invalid_editable_goal_choice(client, field, value):
    goal = create_goal(client)
    revised = {**VALID_GOAL, "name": "Should not save", field: value}

    assert client.put(f"{ROOT}/{goal['id']}", json=revised).status_code == 422
    assert client.get(f"{ROOT}/{goal['id']}").json()["name"] == goal["name"]


@pytest.mark.parametrize("status", ["DONE", "INCOMPLETE", "ARCHIVED", "complete"])
def test_status_change_rejects_every_unrecognized_status(client, status):
    goal = create_goal(client)

    assert client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": status}
    ).status_code == 422
    assert client.get(f"{ROOT}/{goal['id']}").json()["status"] == "NOT_STARTED"


@pytest.mark.parametrize("field", ["status", "completed_at", "active", "owner_id"])
def test_full_edit_cannot_change_status_completion_archive_or_ownership(
    client, field,
):
    goal = create_goal(client)
    completed = client.post(
        f"{ROOT}/{goal['id']}/status", json={"status": "COMPLETED"}
    )
    assert completed.status_code == 200, completed.text
    goal = completed.json()
    original_completed_at = goal["completed_at"]

    assert original_completed_at is not None
    response = client.put(
        f"{ROOT}/{goal['id']}",
        json={**VALID_GOAL, field: (
            "NOT_STARTED" if field == "status"
            else None if field == "completed_at"
            else False if field == "active"
            else "other-workspace"
        )},
    )

    assert response.status_code == 422
    current = client.get(f"{ROOT}/{goal['id']}").json()
    assert current["status"] == "COMPLETED"
    assert current["completed_at"] == original_completed_at
    assert current["active"] is True


@pytest.mark.parametrize(("field", "value"), [
    ("target_amount", "-0.01"),
    ("target_amount", "1.005"),
    ("target_amount", "1000000000000.01"),
    ("target_amount", "NaN"),
    ("target_amount", "Infinity"),
    ("current_progress_amount", "-0.01"),
    ("current_progress_amount", "1.005"),
    ("current_progress_amount", "1000000000000.01"),
    ("current_progress_amount", "NaN"),
    ("current_progress_amount", "Infinity"),
])
def test_target_and_manual_progress_money_is_nonnegative_exact_and_bounded(
    client, field, value,
):
    response = client.post(ROOT, json={**VALID_GOAL, field: value})

    assert response.status_code == 422
    assert client.get(ROOT).json() == []


def test_update_can_clear_optional_values_without_changing_status(client):
    original = create_goal(client)
    started = client.post(
        f"{ROOT}/{original['id']}/status", json={"status": "IN_PROGRESS"}
    )
    assert started.status_code == 200, started.text
    original = started.json()
    update = {
        **VALID_GOAL,
        "name": "An updated goal",
        "description": None,
        "target_date": None,
        "target_amount": None,
        "current_progress_amount": None,
        "notes": None,
    }

    response = client.put(f"{ROOT}/{original['id']}", json=update)

    assert response.status_code == 200, response.text
    changed = response.json()
    assert changed["name"] == "An updated goal"
    assert changed["description"] is None
    assert changed["target_date"] is None
    assert changed["target_amount"] is None
    assert changed["target_amount_cents"] is None
    assert changed["current_progress_amount"] is None
    assert changed["current_progress_amount_cents"] is None
    assert changed["notes"] is None
    assert changed["status"] == "IN_PROGRESS"
    assert changed["completed_at"] is None


@pytest.mark.parametrize("reserved_source", [
    "TRANSACTION_ACTIVITY",
    "ACCOUNT_BALANCE",
    "DEBT_BALANCE",
    "PORTFOLIO_VALUE",
    "INVESTMENT_ACCOUNT",
    "BUSINESS_METRIC",
    "MILESTONES",
])
@pytest.mark.parametrize("amount", ["27.36", "0.00"])
@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_reserved_progress_sources_reject_entered_progress(
    client, reserved_source, amount, method,
):
    before = create_goal(client) if method == "PUT" else None
    url = f"{ROOT}/{before['id']}" if before is not None else ROOT
    response = client.request(method, url, json={
        **VALID_GOAL, "progress_source": reserved_source,
        "current_progress_amount": amount,
    })

    assert response.status_code == 422
    assert "Current progress amount can only be set when progress source is MANUAL." in response.text
    if before is not None:
        assert client.get(url).json() == before
    else:
        assert client.get(ROOT).json() == []


@pytest.mark.parametrize("reserved_source", GOAL_PROGRESS_SOURCES[1:])
@pytest.mark.parametrize("method", ["POST", "PUT"])
@pytest.mark.parametrize("omit_amount", [False, True])
def test_reserved_progress_sources_allow_no_progress_amount(
    client, reserved_source, method, omit_amount,
):
    before = create_goal(client, current_progress_amount=None) if method == "PUT" else None
    url = f"{ROOT}/{before['id']}" if before is not None else ROOT
    payload = {
        **VALID_GOAL, "progress_source": reserved_source,
        "current_progress_amount": None,
    }
    if omit_amount:
        payload.pop("current_progress_amount")
    response = client.request(method, url, json=payload)

    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json()["progress_source"] == reserved_source
    assert response.json()["current_progress_amount"] is None
    assert response.json()["current_progress_amount_cents"] is None


@pytest.mark.parametrize("method", ["POST", "PUT"])
def test_manual_progress_accepts_zero(client, method):
    before = create_goal(client) if method == "PUT" else None
    url = f"{ROOT}/{before['id']}" if before is not None else ROOT
    response = client.request(method, url, json={
        **VALID_GOAL, "current_progress_amount": "0.00",
    })

    assert response.status_code == (201 if method == "POST" else 200)
    assert response.json()["current_progress_amount_cents"] == 0
    assert response.json()["current_progress_amount"] == "0.00"


def test_list_is_owner_scoped_and_active_goals_are_selected_by_default(client):
    active = create_goal(client, name="Active goal")
    archived = create_goal(client, name="Archived goal")
    assert client.post(f"{ROOT}/{archived['id']}/deactivate").status_code == 200

    assert [g["id"] for g in client.get(ROOT).json()] == [active["id"]]
    assert {g["id"] for g in client.get(ROOT + "?active_only=false").json()} == {
        active["id"], archived["id"],
    }


def test_other_workspace_cannot_list_read_edit_archive_reactivate_change_or_delete(
    client,
):
    goal = create_goal(client)
    replacement = {**VALID_GOAL, "name": "A foreign edit"}
    item_url = f"{ROOT}/{goal['id']}"

    with as_workspace("another-test-workspace"):
        assert client.get(ROOT).status_code == 200
        assert client.get(ROOT).json() == []
        assert client.get(ROOT + "?active_only=false").json() == []
        assert client.get(item_url).status_code == 404
        assert client.put(item_url, json=replacement).status_code == 404
        assert client.post(item_url + "/deactivate").status_code == 404
        assert client.post(item_url + "/reactivate").status_code == 404
        assert client.post(
            item_url + "/status", json={"status": "COMPLETED"}
        ).status_code == 404
        assert client.delete(item_url).status_code == 404

    unchanged = client.get(item_url)
    assert unchanged.status_code == 200
    assert unchanged.json()["name"] == goal["name"]
    assert unchanged.json()["status"] == goal["status"]
    assert unchanged.json()["active"] is True


def test_deactivate_hides_goal_and_reactivate_restores_it(client):
    goal = create_goal(client)

    deactivated = client.post(f"{ROOT}/{goal['id']}/deactivate")
    assert deactivated.status_code == 200, deactivated.text
    assert deactivated.json()["active"] is False
    assert client.get(ROOT).json() == []
    assert client.get(f"{ROOT}/{goal['id']}").status_code == 200
    assert [g["id"] for g in client.get(ROOT + "?active_only=false").json()] == [
        goal["id"],
    ]

    reactivated = client.post(f"{ROOT}/{goal['id']}/reactivate")
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["active"] is True
    assert [g["id"] for g in client.get(ROOT).json()] == [goal["id"]]


def test_hard_delete_permanently_removes_the_owned_goal(client):
    goal = create_goal(client)

    response = client.delete(f"{ROOT}/{goal['id']}")

    assert response.status_code == 204
    assert response.content == b""
    assert client.get(f"{ROOT}/{goal['id']}").status_code == 404
    assert client.get(ROOT).json() == []


def _assert_export_has_no_floats(value):
    if isinstance(value, float):
        raise AssertionError(f"export contains a float: {value}")
    if isinstance(value, dict):
        for item in value.values():
            _assert_export_has_no_floats(item)
    elif isinstance(value, list):
        for item in value:
            _assert_export_has_no_floats(item)


def test_full_workspace_export_includes_versioned_active_and_archived_goals(
    client,
):
    active = create_goal(
        client,
        target_date="2028-02-29",
        target_amount="1234.56",
        current_progress_amount="0.01",
    )
    archived = create_goal(
        client,
        name="Archived personal goal",
        goal_type="NONFINANCIAL",
        category="FAMILY",
        target_date=None,
        target_amount=None,
        current_progress_amount=None,
    )
    assert client.post(f"{ROOT}/{archived['id']}/deactivate").status_code == 200

    response = client.get("/serenity-api/export")
    assert response.status_code == 200
    backup = response.json()
    assert backup["format_version"] == 7
    assert len(backup["goals"]) == 2
    by_id = {goal["id"]: goal for goal in backup["goals"]}
    exported = by_id[active["id"]]
    assert exported["id"] == active["id"]
    assert exported["name"] == "Emergency reserve"
    assert exported["goal_type"] == "SAVINGS"
    assert exported["category"] == "FINANCIAL"
    assert exported["status"] == "NOT_STARTED"
    assert exported["priority"] == "NORMAL"
    assert exported["target_date"] == "2028-02-29"
    assert exported["target_amount_cents"] == 123_456
    assert exported["target_amount"] == "1234.56"
    assert exported["current_progress_amount_cents"] == 1
    assert exported["current_progress_amount"] == "0.01"
    assert exported["active"] is True
    assert exported["created_at"] is not None
    assert exported["updated_at"] is not None
    assert by_id[archived["id"]]["active"] is False
    assert by_id[archived["id"]]["target_amount"] is None
    assert by_id[archived["id"]]["target_date"] is None
    _assert_export_has_no_floats(backup)

    with as_workspace("another-test-workspace"):
        foreign_backup = client.get("/serenity-api/export").json()
    assert foreign_backup["goals"] == []