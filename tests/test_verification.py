"""Disposable owner checks: evidence, dates, selection and financial invariance."""

from datetime import timedelta
import json

import pytest
from sqlalchemy import event, select, text

from models.verification import Verification
from services import data_health, verification
from services.identity_service import CLERK_PROVIDER, workspace_for_identity
from tests.conftest import TEST_CLERK_ISSUER, TEST_OWNER_ID, sign_in_as
from tests.test_data_health import NOW, seed_inputs

PATH = "/serenity-api/system/verifications"


def targets(client):
    result = client.get(PATH)
    assert result.status_code == 200, result.text
    assert result.headers["cache-control"] == "no-store"
    return result.json()["targets"]


def payload(target, days=0):
    return {
        "snapshot": target["snapshot"],
        "as_of": (NOW.date() - timedelta(days=days)).isoformat(),
        "evidence": "Synthetic statement checked against displayed fact",
    }


def save(client, target, data=None):
    return client.put(f'{PATH}/{target["kind"]}/{target["target_id"]}',
                      json=data if data is not None else payload(target))


def summary(db, key):
    return next(r for r in data_health.data_health(db, TEST_OWNER_ID)["readings"]
                if r["key"] == key)


def test_empty_missing_and_explicit_zero_not_inferred(client, db):
    assert targets(client) == []
    assert client.get(PATH).json()["retained"] == []
    seed_inputs(db)
    rows = targets(client)
    assert {r["kind"] for r in rows} == {"account_balance", "debt_balance", "legacy_valuation"}
    assert all(r["status"] == "UNKNOWN" and r["verification"] is None for r in rows)
    debt = next(t for t in rows if t["kind"] == "debt_balance")
    assert debt["amount"] == "0.00"
    assert save(client, debt).status_code == 200
    assert next(t for t in targets(client) if t["kind"] == "debt_balance")["status"] == "VERIFIED"


@pytest.mark.parametrize("field,value", [
    ("as_of", None), ("as_of", "not-a-date"),
    ("as_of", "2999-01-01"), ("evidence", ""), ("evidence", "   "),
    ("evidence", "x" * 1001), ("snapshot", "bad"), ("owner_id", "foreign"),
    ("balance", "999.99"),
])
def test_invalid_missing_future_evidence_rejected(client, db, field, value):
    seed_inputs(db)
    target = targets(client)[0]
    data = payload(target)
    data[field] = value
    response = save(client, target, data)
    assert response.status_code == 422
    assert response.headers["cache-control"] == "no-store"
    assert db.scalar(select(Verification)) is None


@pytest.mark.parametrize("field", ["as_of", "evidence", "snapshot"])
def test_required_fields_have_no_default(client, db, field):
    seed_inputs(db)
    target = targets(client)[0]
    data = payload(target)
    del data[field]
    assert save(client, target, data).status_code == 422


def test_replace_delete_no_financial_writes_and_summary_redacted(client, db):
    rows = seed_inputs(db)
    before = [(r.updated_at, r.notes) for r in rows]
    target = next(t for t in targets(client) if t["kind"] == "debt_balance")
    statements = []
    def capture(conn, cursor, statement, parameters, context, many):
        statements.append(statement.strip().upper())
    engine = db.get_bind()
    event.listen(engine, "before_cursor_execute", capture)
    try:
        first = save(client, target).json()
        changed = payload(target)
        changed["evidence"] = "<img src=x onerror=alert(1)> private owner evidence"
        second = save(client, target, changed).json()
        assert first["id"] == second["id"]
        assert len(db.scalars(select(Verification)).all()) == 1
        assert "private owner evidence" not in json.dumps(summary(db, "debts"))
        assert client.delete(f'{PATH}/{first["id"]}').status_code == 204
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    assert all("MANUAL_VERIFICATIONS" in s for s in statements
               if s.startswith(("INSERT", "UPDATE", "DELETE")))
    assert before == [(r.updated_at, r.notes) for r in rows]
    assert next(t for t in targets(client) if t["kind"] == "debt_balance")["status"] == "UNKNOWN"


def test_notes_do_not_verify_or_refresh_and_fact_changes_invalidate(client, db):
    rows = seed_inputs(db)
    debt = next(t for t in targets(client) if t["kind"] == "debt_balance")
    rows[2].notes = "Just edited notes"
    db.commit()
    assert next(t for t in targets(client) if t["kind"] == "debt_balance")["status"] == "UNKNOWN"
    saved = save(client, debt, payload(debt, days=30)).json()
    rows[2].notes = "More notes"
    db.commit()
    current = next(t for t in targets(client) if t["kind"] == "debt_balance")
    assert current["snapshot"] == debt["snapshot"]
    assert current["status"] == "STALE"
    assert current["verification"]["recorded_at"] == saved["recorded_at"]
    rows[2].balance_cents = 100
    db.commit()
    assert next(t for t in targets(client) if t["kind"] == "debt_balance")["status"] == "CHANGED"
    assert save(client, debt).status_code == 409
    assert "verification_changed" in {f["code"] for f in summary(db, "debts")["findings"]}


def test_exact_30_day_review_reminder_supersedes_edit_age(client, db):
    rows = seed_inputs(db)
    rows[2].updated_at = NOW - timedelta(days=100)
    db.commit()
    target = next(t for t in targets(client) if t["kind"] == "debt_balance")
    save(client, target, payload(target, days=29))
    # API records now; this deterministic observation must be later than recording.
    db.scalar(select(Verification)).recorded_at = NOW
    db.commit()
    reading = summary(db, "debts")
    assert reading["status"] == "MANUAL"
    assert "review_due" not in {f["code"] for f in reading["findings"]}
    save(client, target, payload(target, days=30))
    db.scalar(select(Verification)).recorded_at = NOW
    db.commit()
    assert summary(db, "debts")["status"] == "STALE"


def test_future_persisted_evidence_is_not_verification(client, db):
    seed_inputs(db)
    t = next(t for t in targets(client) if t["kind"] == "debt_balance")
    save(client, t)
    db.execute(text("UPDATE manual_verifications SET as_of='2999-01-01'"))
    db.commit()
    assert next(t for t in targets(client) if t["kind"] == "debt_balance")["status"] == "INCONSISTENT"
    assert summary(db, "debts")["status"] == "INCONSISTENT"


def test_deleted_sources_evidence_retained_and_id_reuse_never_verifies(client, db):
    rows = seed_inputs(db)
    t = next(t for t in targets(client) if t["kind"] == "debt_balance")
    evidence = save(client, t).json()
    db.delete(rows[2])
    db.commit()
    report = client.get(PATH).json()
    assert report["retained"][0]["id"] == evidence["id"]
    assert all(x["kind"] != "debt_balance" for x in report["targets"])
    assert save(client, t).status_code == 404
    from models.debt import Debt
    db.add(Debt(id=t["target_id"], owner_id=TEST_OWNER_ID, name="New generation", balance_cents=0))
    db.commit()
    assert next(t for t in targets(client) if t["kind"] == "debt_balance")["status"] == "CHANGED"
    assert client.delete(f'{PATH}/{evidence["id"]}').status_code == 204


def test_conversion_opening_check_does_not_edit_ledger_or_capture(client, db):
    from tests.test_conversion_readers import _converted_fixture
    account, source, _, opening = _converted_fixture(db)
    account.account_type = "Brokerage"
    db.commit()
    before = (opening.captured_at, opening.valuation_as_of_date, opening.valuation_evidence,
              opening.original_entered_value_cents)
    ts = targets(client)
    assert not any(t["kind"] == "legacy_valuation" and t["target_id"] == source.id for t in ts)
    t = next(t for t in ts if t["kind"] == "opening_valuation")
    assert save(client, t).status_code == 200
    assert next(t for t in targets(client) if t["kind"] == "opening_valuation")["status"] == "VERIFIED"
    assert before == (opening.captured_at, opening.valuation_as_of_date, opening.valuation_evidence,
                      opening.original_entered_value_cents)
    opening.status = "reversed"
    db.commit()
    assert client.get(PATH).status_code == 503


def test_unreadable_evidence_is_not_empty_and_does_not_change_runtime(client, db):
    seed_inputs(db)
    db.execute(text("DROP TABLE manual_verifications"))
    db.commit()
    assert client.get(PATH).status_code == 503
    health = client.get("/serenity-api/system/health").json()
    assert health["state"] == "NORMAL"
    assert health["data_health"]["readings"][2]["status"] == "UNAVAILABLE"


def test_account_transactions_change_snapshot_but_descriptions_do_not(client, db):
    from models.transaction import Transaction
    account, *_ = seed_inputs(db)
    t = next(t for t in targets(client) if t["kind"] == "account_balance")
    save(client, t)
    tx = Transaction(owner_id=TEST_OWNER_ID, account_id=account.id, date=NOW.date(),
                     transaction_type="Income", classification="Personal",
                     amount_cents=100, description="Synthetic")
    db.add(tx)
    db.commit()
    current = next(t for t in targets(client) if t["kind"] == "account_balance")
    assert current["amount"] == "1.00" and current["status"] == "CHANGED"
    save(client, current)
    tx.description = "Description only"
    db.commit()
    assert next(t for t in targets(client) if t["kind"] == "account_balance")["status"] == "VERIFIED"


def test_valuation_quantity_and_selection_changes_do_not_inherit_check(client, db):
    rows = seed_inputs(db)
    t = next(t for t in targets(client) if t["kind"] == "legacy_valuation")
    save(client, t)
    rows[3].quantity_units = 100000000
    db.commit()
    assert next(t for t in targets(client) if t["kind"] == "legacy_valuation")["status"] == "CHANGED"
    rows[3].review_pending = True
    db.commit()
    assert save(client, t).status_code == 404
    assert client.get(PATH).json()["retained"][0]["kind"] == "legacy_valuation"


def test_opening_check_only_supersedes_its_own_reminder(client, db):
    from tests.test_conversion_readers import _converted_fixture
    account, _, _, _ = _converted_fixture(db)
    account.account_type = "Brokerage"
    db.commit()
    t = next(t for t in targets(client) if t["kind"] == "opening_valuation")
    save(client, t)
    codes = {f["code"] for f in summary(db, "investments")["findings"]}
    assert "owner_verified" in codes
    assert "verification_unknown" in codes  # Other selected legacy value remains unchecked.
    assert "unknown_valuation_date" not in codes


def test_future_source_edit_rejected_in_private_review_too(client, db):
    rows = seed_inputs(db)
    rows[2].updated_at = NOW + timedelta(days=2)
    db.commit()
    assert client.get(PATH).status_code == 503
    assert summary(db, "debts")["status"] == "INCONSISTENT"


@pytest.mark.parametrize("damage", ["future_date", "missing_evidence"])
def test_opening_source_date_corruption_cannot_be_overridden(client, db, damage):
    from tests.test_conversion_readers import _converted_fixture
    account, _, _, opening = _converted_fixture(db)
    account.account_type = "Brokerage"
    db.commit()
    t = next(t for t in targets(client) if t["kind"] == "opening_valuation")
    opening.valuation_as_of_date = NOW.date() + timedelta(days=2) if damage == "future_date" else NOW.date()
    opening.valuation_evidence = "Synthetic" if damage == "future_date" else None
    db.commit()
    assert client.get(PATH).status_code == 503
    assert save(client, t).status_code == 503
    assert db.scalar(select(Verification)) is None


def test_real_owner_isolation_and_no_caller_owner(real_auth_client, db):
    owners = [workspace_for_identity(
        db, provider=CLERK_PROVIDER, issuer=TEST_CLERK_ISSUER, subject=s,
    ) for s in ("verification-a", "verification-b")]
    seed_inputs(db, owners[0])
    seed_inputs(db, owners[1])
    sign_in_as(real_auth_client, "verification-a")
    t = targets(real_auth_client)[0]
    saved = save(real_auth_client, t).json()
    sign_in_as(real_auth_client, "verification-b")
    assert save(real_auth_client, t).status_code == 404
    assert real_auth_client.delete(f'{PATH}/{saved["id"]}').status_code == 404
    report = real_auth_client.get(PATH + "?owner_id=" + owners[0]).json()
    assert all(t["verification"] is None for t in report["targets"])
    real_auth_client.cookies.clear()
    assert real_auth_client.get(PATH).status_code == 401
    assert save(real_auth_client, t).status_code == 401
    assert real_auth_client.delete(f'{PATH}/{saved["id"]}').status_code == 401