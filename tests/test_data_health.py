"""Disposable financial input evidence: owner scope, invalid rows and no writes."""

from datetime import datetime, timedelta, timezone
import json

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from models.account import Account
from models.bill import Bill
from models.debt import Debt
from models.income_profile import IncomeProfile
from models.investment import Investment
from models.transaction import Transaction
from services import data_health, finance_service
from services.identity_service import CLERK_PROVIDER, workspace_for_identity
from tests.conftest import TEST_CLERK_ISSUER, TEST_OWNER_ID, sign_in_as

PATH = "/serenity-api/system/health"
NOW = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)


def readings(client):
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    return {r["key"]: r for r in response.json()["data_health"]["readings"]}


def codes(reading):
    return {f["code"] for f in reading["findings"]}


def seed_inputs(db, owner=TEST_OWNER_ID):
    rows = [
        Account(owner_id=owner, name="Private checking", account_type="Checking",
                classification="Personal", opening_balance_cents=0),
        Bill(owner_id=owner, name="Private bill", due_date=NOW.date() + timedelta(days=7),
             amount_cents=0, frequency="Monthly"),
        Debt(owner_id=owner, name="Private debt", balance_cents=0),
        Investment(owner_id=owner, name="Private shares", current_value_cents=0),
        IncomeProfile(owner_id=owner, name="Private salary", income_type="Salary",
                      annual_salary_cents=6_000_000, pay_frequency="Monthly"),
    ]
    for row in rows:
        row.created_at = NOW - timedelta(days=1)
        row.updated_at = NOW - timedelta(days=1)
    db.add_all(rows)
    db.commit()
    return rows


def test_empty_data_is_missing_not_confirmed_zero(client):
    data = readings(client)
    assert set(data) == {"accounts", "bills", "debts", "investments", "income"}
    for r in data.values():
        assert r["status"] == "MISSING"
        assert r["record_count"] == 0
        assert "not confirmation" in r["findings"][0]["message"]
    assert data["income"]["basis"] == data["bills"]["basis"] == "PLANNED"
    assert data["accounts"]["basis"] == data["debts"]["basis"] == "ACTUAL"


def test_zero_records_are_manual_inputs_not_missing_and_plans_are_distinct(client, db):
    seed_inputs(db)
    data = readings(client)
    assert data["debts"]["status"] == "PARTIAL"
    assert data["investments"]["status"] == "PARTIAL"
    assert "verification_unknown" in codes(data["debts"])
    assert all(r["record_count"] == 1 for r in data.values())
    assert "opening_only" in codes(data["accounts"])
    assert "missing_take_home" in codes(data["income"])
    assert "planned_not_received" in codes(data["income"])
    assert "scheduled_not_paid" in codes(data["bills"])
    assert "selected_valuations" in codes(data["investments"])
    output = json.dumps(data)
    assert "Private" not in output
    assert "6000000" not in output
    assert TEST_OWNER_ID not in output
    assert "score" not in data


def test_partial_net_and_variable_income_use_canonical_projection_semantics(client, db):
    seed_inputs(db)
    db.add_all([
        IncomeProfile(owner_id=TEST_OWNER_ID, name="Net known", income_type="Salary",
                      annual_salary_cents=5_000_000, pay_frequency="Monthly",
                      expected_net_per_period_cents=200_000),
        IncomeProfile(owner_id=TEST_OWNER_ID, name="Variable", income_type="Variable"),
    ])
    db.commit()
    r = readings(client)["income"]
    assert r["status"] == "PARTIAL"
    assert {"variable_not_projected", "missing_take_home"} <= codes(r)
    assert "unknown or partial" in json.dumps(r)


def test_actual_transactions_do_not_turn_forecast_into_receipts(client, db):
    account, *_ = seed_inputs(db)
    db.add(Transaction(
        owner_id=TEST_OWNER_ID, account_id=account.id, date=NOW.date(),
        transaction_type="Income", classification="Personal",
        amount_cents=1000, description="Synthetic receipt",
    ))
    db.commit()
    data = readings(client)
    assert data["accounts"]["status"] == "PARTIAL"
    assert "opening_only" not in codes(data["accounts"])
    assert "planned_not_received" in codes(data["income"])
    assert "Synthetic receipt" not in json.dumps(data)


def test_staleness_has_disclosed_exact_threshold_and_uses_utc(db):
    rows = seed_inputs(db)
    for row in rows:
        row.updated_at = NOW - timedelta(days=30)
    # Plans still require missing-net review independently of age.
    rows[-1].expected_net_per_period_cents = 1000
    db.commit()
    observed = data_health.data_health(db, TEST_OWNER_ID, now=NOW)
    data = {r["key"]: r for r in observed["readings"]}
    assert data["debts"]["status"] == data["income"]["status"] == "STALE"
    assert "review_due" in codes(data["investments"])
    assert "30 or more days" in json.dumps(data)
    assert "not proof" in json.dumps(data)
    rows[2].updated_at = NOW - timedelta(days=30) + timedelta(seconds=1)
    db.commit()
    r = data_health.data_health(db, TEST_OWNER_ID, now=NOW)["readings"][2]
    assert r["status"] == "PARTIAL"
    assert "review_due" not in codes(r)


def test_due_schedule_reminder_never_claims_unpaid_bill(client, db):
    rows = seed_inputs(db)
    rows[1].due_date = NOW.date() - timedelta(days=1)
    db.commit()
    r = readings(client)["bills"]
    assert r["status"] == "STALE"
    assert "past_due_schedule" in codes(r)
    assert "does not prove a missed payment" in json.dumps(r)


@pytest.mark.parametrize("index", range(5))
def test_only_inactive_inputs_are_partial_not_empty(client, db, index):
    rows = seed_inputs(db)
    rows[index].active = False
    db.commit()
    r = list(readings(client).values())[index]
    assert r["status"] == "PARTIAL"
    assert r["record_count"] == 1
    assert "no_active_inputs" in codes(r)


@pytest.mark.parametrize("index,attribute,value", [
    (0, "classification", "Not a classification"),
    (1, "frequency", "Bogus"),
    (2, "balance_cents", -1),
    (3, "quantity_units", -1),
    (4, "annual_salary_cents", None),
    (2, "updated_at", NOW + timedelta(days=2)),
])
def test_malformed_persisted_inputs_are_inconsistent_not_zero(client, db, index, attribute, value):
    rows = seed_inputs(db)
    setattr(rows[index], attribute, value)
    db.commit()
    data = readings(client)
    r = list(data.values())[index]
    assert r["status"] == "INCONSISTENT"
    assert r["record_count"] is None
    assert "invalid_inputs" in codes(r)
    assert all(other["status"] != "UNAVAILABLE" for other in data.values())
    assert "Private" not in json.dumps(data)


def test_orphaned_or_cross_workspace_actual_transaction_is_inconsistent(client, db):
    foreign = Account(owner_id="other-owner", name="Hidden", account_type="Checking",
                      classification="Personal")
    db.add(foreign)
    db.commit()
    db.add(Transaction(
        owner_id=TEST_OWNER_ID, account_id=foreign.id, date=NOW.date(),
        transaction_type="Income", classification="Personal", amount_cents=100,
        description="Must not be exposed",
    ))
    db.commit()
    r = readings(client)["accounts"]
    assert r["status"] == "INCONSISTENT"
    assert r["record_count"] is None
    assert "Hidden" not in json.dumps(r)
    assert "Must not be exposed" not in json.dumps(r)


def test_missing_owned_portfolio_link_is_inconsistent(client, db):
    rows = seed_inputs(db)
    rows[3].portfolio_id = 98765
    db.commit()
    assert readings(client)["investments"]["status"] == "INCONSISTENT"


def test_review_pending_candidate_is_not_an_actual_counted_asset(client, db):
    rows = seed_inputs(db)
    rows[3].review_pending = True
    db.commit()
    r = readings(client)["investments"]
    assert r["status"] == "PARTIAL"
    assert "pending_review" in codes(r)
    assert "excluded from net worth" in json.dumps(r)


def test_converted_values_use_selected_opening_not_stale_retained_source(client, db):
    from tests.test_conversion_readers import _converted_fixture
    _, source, _, opening = _converted_fixture(db)
    source.updated_at = NOW - timedelta(days=100)
    opening.basis_status = "unknown"
    opening.entered_basis_cents = None
    db.commit()
    r = readings(client)["investments"]
    assert r["status"] == "PARTIAL"
    assert "unknown_cost_basis" in codes(r)
    assert "review_due" not in codes(r)
    assert "unknown_valuation_date" in codes(r)
    db.execute(text("UPDATE opening_positions SET status='reversed'"))
    db.commit()
    assert readings(client)["investments"]["status"] == "INCONSISTENT"


def test_dated_opening_uses_valuation_date_not_capture_time(client, db):
    from tests.test_conversion_readers import _converted_fixture
    _, _, _, opening = _converted_fixture(db)
    opening.valuation_as_of_date = NOW.date() - timedelta(days=31)
    opening.valuation_evidence = "Synthetic dated statement"
    db.commit()
    r = readings(client)["investments"]
    assert r["status"] == "STALE"
    assert "valuation_review_due" in codes(r)
    assert "Synthetic dated statement" not in json.dumps(r)
    opening.valuation_evidence = None
    db.commit()
    assert readings(client)["investments"]["status"] == "INCONSISTENT"


def test_unavailable_domain_is_redacted_and_never_returns_zero(client, db, monkeypatch):
    seed_inputs(db)

    def fail(*args):
        raise OperationalError("private-host", {"record": "private-amount"}, Exception("secret"))

    monkeypatch.setattr(finance_service, "list_debts", fail)
    response = client.get(PATH)
    assert response.json()["state"] == "NORMAL"
    data = {r["key"]: r for r in response.json()["data_health"]["readings"]}
    assert data["debts"]["status"] == "UNAVAILABLE"
    assert data["debts"]["record_count"] is None
    assert data["investments"]["record_count"] == 1
    assert not any(s in response.text for s in ("private-host", "private-amount", "secret"))


def test_evidence_requests_do_not_mutate_financial_rows_or_take_write_locks(client, db, monkeypatch):
    from services import financial_write_lock
    seed_inputs(db)
    monkeypatch.setattr(financial_write_lock, "lock_owner_financial_writes",
                        lambda *a, **k: pytest.fail("Evidence must not take write locks"))
    # Services bind their imported lock functions separately.
    for module in (finance_service, data_health.account_service,
                   data_health.income_profile_service, data_health.portfolio_service):
        monkeypatch.setattr(module, "lock_owner_financial_writes",
                            lambda *a, **k: pytest.fail("Evidence must not take write locks"))
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement.strip().upper())
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        readings(client)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert not any(s.startswith(("CREATE", "ALTER", "DROP"))
                   or "FOR UPDATE" in s for s in statements)
    for statement in statements:
        if statement.startswith(("INSERT", "UPDATE", "DELETE")):
            # The System endpoint now has a separate operational audit. Data
            # Health remains observational: no financial rows may be mutated.
            assert "WORKSPACES" in statement or "SYSTEM_OBSERVATIONS" in statement


def test_verified_owner_scope_ignores_caller_workspace_and_foreign_damage(real_auth_client, db):
    owners = [
        workspace_for_identity(db, provider=CLERK_PROVIDER, issuer=TEST_CLERK_ISSUER, subject=s)
        for s in ("health-actual-a", "health-actual-b")
    ]
    seed_inputs(db, owners[0])
    # Owner B's malformed dataset must not influence A's evidence.
    rows = seed_inputs(db, owners[1])
    rows[2].balance_cents = -1
    db.commit()
    sign_in_as(real_auth_client, "health-actual-a")
    response = real_auth_client.get(PATH + "?owner_id=" + owners[1])
    data = {r["key"]: r for r in response.json()["data_health"]["readings"]}
    assert data["debts"]["status"] == "PARTIAL"
    assert all(r["record_count"] == 1 for r in data.values())
    assert not any(owner in response.text for owner in owners)
    sign_in_as(real_auth_client, "health-actual-b")
    assert readings(real_auth_client)["debts"]["status"] == "INCONSISTENT"