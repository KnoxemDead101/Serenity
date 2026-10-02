"""Isolated conversion API tests; synthetic evidence is explicitly test-gated."""

import hashlib
import json
import pytest
from datetime import datetime, timedelta, timezone

from models.conversion import (
    CashReconciliationEntry, ConversionEvent, OpeningPosition, ReconciliationApproval,
    ValuationEligibility,
)
from models.investment import Investment


ROOT = "/serenity-api"


@pytest.mark.parametrize("direct_portfolio", [True, False])
@pytest.mark.parametrize("meaning", ["cash_only", "combined"])
def test_pending_draft_exact_reviewed_opening_and_reversal(
    client, db, monkeypatch, direct_portfolio, meaning,
):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, legacy, _ = setup_report(
        client, balance="2000" if meaning == "cash_only" else "10000",
        meaning=meaning,
    )
    assert client.delete(ROOT + f"/investments/{legacy['id']}").status_code == 204
    container = client.get(ROOT + "/investment-accounts").json()[0]
    instrument = client.get(ROOT + "/instruments").json()[0]
    source = create(
        client, "investments", name="Pending reviewed draft", ticker="ACME",
        quantity="40", cost_basis="6000", current_value="8000",
        **({"portfolio_id": container["portfolio_id"]} if direct_portfolio
           else {"investment_account_id": container["id"]}),
    )
    assert source["review_pending"] is True
    original = db.query(Investment).filter_by(id=source["id"]).one()
    raw_before = (original.quantity_units, original.cost_basis_cents,
                  original.current_value_cents, original.review_pending,
                  original.portfolio_id, original.investment_account_id)
    mapping = {
        "source_id": source["id"], "investment_account_id": container["id"],
        "instrument_id": instrument["id"], "specification_id": instrument["specification_id"],
        "identity_confirmed": True, "beneficial_ownership": "personal",
    }
    if direct_portfolio:
        mapping.update(portfolio_id=container["portfolio_id"], account_id=account["id"])
    draft = {
        "mappings": [mapping],
        "accounts": [{
            "account_id": account["id"], "balance_meaning": meaning,
            "cash_cents": 200000, "source_ids": [source["id"]],
            "complete": True, "evidence": "Synthetic complete draft statement",
        }],
    }
    if direct_portfolio:
        # A direct portfolio/account review does not silently create or infer a link.
        unresolved = {**draft, "mappings": [{**mapping, "investment_account_id": None}]}
        incomplete = client.post(ROOT + "/reconciliation/execution-preview", json=unresolved)
        assert incomplete.status_code == 200, incomplete.text
        assert incomplete.json()["report"]["sources"][0]["outcome"] == "unresolved"
        legacy_preview = client.post(ROOT + "/reconciliation/preview", json=unresolved)
        assert legacy_preview.status_code == 200, legacy_preview.text
        assert legacy_preview.json()["report"]["proposed"]["holding_value_cents"] == 800000
        mismatched = {**draft, "mappings": [{**mapping, "account_id": None}]}
        assert client.post(ROOT + "/reconciliation/execution-preview", json=mismatched).status_code == 404
    preview = client.post(ROOT + "/reconciliation/execution-preview", json=draft)
    assert preview.status_code == 200, preview.text
    report = preview.json()["report"]
    assert report["sources"][0]["outcome"] == "eligible"
    assert report["current"]["legacy_investment_cents"] == 0
    assert report["proposed"]["holding_value_cents"] == 800000
    assert report["delta_cents"] == (800000 if meaning == "cash_only" else 0)
    approved = client.post(ROOT + "/conversions/approvals", json=approval_body(
        preview.json(), source["id"], account["id"], test_mode=True,
    ))
    assert approved.status_code == 201, approved.text
    approval_id = approved.json()["approval_id"]
    executed = client.post(ROOT + f"/conversions/{approval_id}/execute", json={
        "idempotency_key": "synthetic-pending-draft", "confirm_execute": True,
    })
    assert executed.status_code == 200, executed.text
    assert executed.json()["after_totals"] == report["proposed"]
    assert client.get(ROOT + f"/investments/{source['id']}").json()["read_only"] is True
    original = db.query(Investment).filter_by(id=source["id"]).one()
    assert raw_before == (original.quantity_units, original.cost_basis_cents,
                         original.current_value_cents, original.review_pending,
                         original.portfolio_id, original.investment_account_id)
    restored = client.post(ROOT + f"/conversions/{approval_id}/reverse", json={
        "reason": "Synthetic draft rollback", "confirm_reverse": True,
    })
    assert restored.status_code == 200, restored.text
    assert restored.json()["after_totals"] == report["current"]
    assert client.get(ROOT + f"/investments/{source['id']}").json()["review_pending"] is True


def test_new_goal_dependency_blocks_stale_approval_and_later_reversal(client, monkeypatch):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, source, preview = setup_report(client)
    approved = client.post(ROOT + "/conversions/approvals", json=approval_body(
        preview, source["id"], account["id"], test_mode=True,
    ))
    assert approved.status_code == 201, approved.text
    create(client, "goals", name="Synthetic financial plan", goal_type="SAVINGS",
           category="FINANCIAL", target_amount="1000",
           progress_source="MANUAL", current_progress_amount="0")
    stale = client.post(ROOT + f"/conversions/{approved.json()['approval_id']}/execute", json={
        "idempotency_key": "synthetic-goal-stale", "confirm_execute": True,
    })
    assert stale.status_code == 409
    refreshed = client.post(ROOT + "/reconciliation/execution-preview", json={
        "mappings": [preview["report"]["sources"][0]["mapping"]],
        "accounts": [preview["report"]["accounts"][0]["evidence"]],
    })
    assert refreshed.status_code == 200, refreshed.text
    fresh_approval = client.post(ROOT + "/conversions/approvals", json=approval_body(
        refreshed.json(), source["id"], account["id"], test_mode=True,
    ))
    assert fresh_approval.status_code == 201, fresh_approval.text
    approval_id = fresh_approval.json()["approval_id"]
    executed = client.post(ROOT + f"/conversions/{approval_id}/execute", json={
        "idempotency_key": "synthetic-goal-fresh", "confirm_execute": True,
    })
    assert executed.status_code == 200, executed.text
    later_goal = create(client, "goals", name="Later synthetic plan", goal_type="SAVINGS",
                        category="FINANCIAL", target_amount="1000", progress_source="MANUAL")
    blocked = client.post(ROOT + f"/conversions/{approval_id}/reverse", json={
        "reason": "Synthetic changed dependency", "confirm_reverse": True,
    })
    assert blocked.status_code == 409, blocked.text
    assert str(later_goal["id"]) in json.dumps(blocked.json())


def create(client, path, **fields):
    response = client.post(ROOT + "/" + path, json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def setup_report(client, balance="10000", meaning="combined", cash=200000, symbol="ACME"):
    account = create(
        client, "accounts", name="Brokerage", account_type="Brokerage",
        classification="Personal", opening_balance=balance,
    )
    portfolio = create(client, "portfolios", name="Investments")
    container = create(
        client, "investment-accounts", name="Brokerage sleeve",
        portfolio_id=portfolio["id"], account_id=account["id"],
    )
    instrument = create(client, "instruments", symbol=symbol, name=symbol, asset_type="STOCK")
    source = create(
        client, "investments", name="Original shares", ticker=symbol,
        quantity="40", cost_basis="6000", current_value="8000",
    )
    preview = client.post(ROOT + "/reconciliation/execution-preview", json={
        "mappings": [{
            "source_id": source["id"], "investment_account_id": container["id"],
            "instrument_id": instrument["id"], "specification_id": instrument["specification_id"],
            "identity_confirmed": True, "beneficial_ownership": "personal",
            "basis_status": "unverified",
        }],
        "accounts": [{
            "account_id": account["id"], "balance_meaning": meaning, "cash_cents": cash,
            "evidence": "Synthetic statement", "complete": True,
            "source_ids": [source["id"]],
        }],
    })
    assert preview.status_code == 200, preview.text
    return account, source, preview.json()


def approval_body(preview, source_id, account_id, test_mode=False):
    report = preview["report"]
    digest = hashlib.sha256(
        json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
    ).hexdigest()
    account_report = next(row for row in report["accounts"] if row["account"]["id"] == account_id)
    now = datetime.now(timezone.utc)
    return {
        "report_token": preview["report_token"], "report_sha256": digest,
        "selected_source_ids": [source_id],
        "account_corrections_cents": {str(account_id): account_report["correction_cents"]},
        "backup_evidence_reference": "synthetic://isolated-test-backup",
        "backup_cutoff": (now - timedelta(minutes=5)).isoformat(),
        "rollback_deadline": (now + timedelta(days=1)).isoformat(),
        "confirm_approval": True, "test_only_synthetic": test_mode,
    }


def test_production_approval_fails_closed_without_verified_off_host_backup(client):
    account, source, preview = setup_report(client)
    request = approval_body(preview, source["id"], account["id"])
    response = client.post(ROOT + "/conversions/approvals", json=request)
    assert response.status_code == 503, response.text
    assert response.json()["detail"]


def test_synthetic_approval_execution_retry_evidence_and_safe_reversal(client, db, monkeypatch):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, source, preview = setup_report(client)
    report = preview["report"]
    assert report["format_version"] == 2 and report["executable"] is True
    request = approval_body(preview, source["id"], account["id"], test_mode=True)
    approved = client.post(ROOT + "/conversions/approvals", json=request)
    assert approved.status_code == 201, approved.text
    approval_id = approved.json()["approval_id"]
    assert approved.json()["state"] == "approved"
    assert db.query(Investment).filter_by(id=source["id"]).one().active is True

    execute_payload = {"idempotency_key": "synthetic-execute-0001", "confirm_execute": True}
    executed = client.post(
        ROOT + f"/conversions/{approval_id}/execute", json=execute_payload,
    )
    assert executed.status_code == 200, executed.text
    result = executed.json()
    assert result["event_kind"] == "executed"
    assert result["after_totals"]["net_worth_cents"] == report["proposed"]["net_worth_cents"]
    assert result["after_totals"]["account_balance_cents"] == 200000
    retry = client.post(ROOT + f"/conversions/{approval_id}/execute", json=execute_payload)
    assert retry.status_code == 200 and retry.json() == result
    conflict = client.post(ROOT + f"/conversions/{approval_id}/execute", json={
        "idempotency_key": "synthetic-execute-0002", "confirm_execute": True,
    })
    assert conflict.status_code == 409

    evidence = client.get(ROOT + f"/conversions/{approval_id}/evidence")
    assert evidence.status_code == 200
    assert evidence.headers["cache-control"] == "no-store"
    body = evidence.json()
    assert body["approval"]["report_sha256"] == approved.json()["report_sha256"]
    assert len(body["opening_positions"]) == 1
    assert len(body["cash_entries"]) == 1
    assert db.query(OpeningPosition).count() == 1
    assert db.query(ValuationEligibility).one().representation == "opening"
    assert db.query(CashReconciliationEntry).filter_by(reason="combined_balance_overlap").count() == 1
    assert db.query(ConversionEvent).filter_by(event_kind="executed").count() == 1
    legacy_review = client.post(ROOT + "/reconciliation/preview", json={
        "mappings": [], "accounts": [],
    })
    assert legacy_review.status_code == 200, legacy_review.text
    assert any("Legacy format 1 semantics" in warning
               for warning in legacy_review.json()["report"]["warnings"])
    assert client.post(ROOT + "/reconciliation/verify", json={
        "report_token": legacy_review.json()["report_token"],
    }).json()["stale"] is False
    later_batch_preview = client.post(ROOT + "/reconciliation/execution-preview", json={
        "mappings": [], "accounts": [],
    })
    assert later_batch_preview.status_code == 200, later_batch_preview.text
    assert later_batch_preview.json()["report"]["current"]["net_worth_cents"] == 1000000
    assert later_batch_preview.json()["report"]["current"]["holding_value_cents"] == 800000

    reverse_body = {"reason": "Synthetic test reversal", "confirm_reverse": True}
    reversed_result = client.post(
        ROOT + f"/conversions/{approval_id}/reverse", json=reverse_body,
    )
    assert reversed_result.status_code == 200, reversed_result.text
    assert reversed_result.json()["event_kind"] == "reversed"
    assert client.post(
        ROOT + f"/conversions/{approval_id}/reverse", json=reverse_body,
    ).json() == reversed_result.json()
    assert db.query(OpeningPosition).one().status == "reversed"
    assert db.query(ValuationEligibility).one().representation == "legacy"
    assert db.query(CashReconciliationEntry).filter_by(reason="conversion_reversal").count() == 1
    assert db.query(ConversionEvent).filter_by(event_kind="reversed").count() == 1
    assert client.get(ROOT + f"/conversions/{approval_id}").json()["approval"]["state"] == "reversed"


def test_stale_report_and_unconfirmed_approval_or_execution(client, db, monkeypatch):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, source, preview = setup_report(client)
    # Change a fingerprinted source before approval.
    changed = client.put(ROOT + f"/investments/{source['id']}", json={
        "name": "Edited", "ticker": "ACME", "quantity": "40",
        "cost_basis": "6000", "current_value": "8000.01",
    })
    assert changed.status_code == 200
    stale = client.post(ROOT + "/conversions/approvals", json=approval_body(
        preview, source["id"], account["id"], test_mode=True,
    ))
    assert stale.status_code == 409
    assert db.query(ReconciliationApproval).count() == 0


def test_clean_cash_only_numeric_components_are_preserved(client, db, monkeypatch):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, source, preview = setup_report(
        client, balance="2000", meaning="cash_only", cash=200000,
    )
    report = preview["report"]
    assert report["current"] == {
        "account_balance_cents": 200000, "legacy_investment_cents": 800000,
        "holding_value_cents": 0, "debt_balance_cents": 0,
        "net_worth_cents": 1000000,
    }
    assert report["proposed"] == {
        "account_balance_cents": 200000, "legacy_investment_cents": 0,
        "holding_value_cents": 800000, "debt_balance_cents": 0,
        "net_worth_cents": 1000000,
    }
    approved = client.post(ROOT + "/conversions/approvals", json=approval_body(
        preview, source["id"], account["id"], test_mode=True,
    ))
    assert approved.status_code == 201, approved.text
    response = client.post(
        ROOT + f"/conversions/{approved.json()['approval_id']}/execute",
        json={"idempotency_key": "clean-cash-only-0001", "confirm_execute": True},
    )
    assert response.status_code == 200, response.text
    assert response.json()["before_totals"] == report["current"]
    assert response.json()["after_totals"] == report["proposed"]
    assert response.json()["after_totals"]["net_worth_cents"] == 1000000
    assert db.query(CashReconciliationEntry).count() == 0


def test_disjoint_later_batch_includes_prior_openings_and_totals(client, db, monkeypatch):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    first_account, first_source, first_preview = setup_report(client, symbol="FIRST")
    first_approval = client.post(
        ROOT + "/conversions/approvals",
        json=approval_body(first_preview, first_source["id"], first_account["id"], test_mode=True),
    )
    assert first_approval.status_code == 201, first_approval.text
    first_execution = client.post(
        ROOT + f"/conversions/{first_approval.json()['approval_id']}/execute",
        json={"idempotency_key": "first-batch-execution", "confirm_execute": True},
    )
    assert first_execution.status_code == 200, first_execution.text

    second_account, second_source, second_preview = setup_report(client, symbol="SECOND")
    second_report = second_preview["report"]
    assert second_report["current"] == {
        "account_balance_cents": 1200000, "legacy_investment_cents": 800000,
        "holding_value_cents": 800000, "debt_balance_cents": 0,
        "net_worth_cents": 2800000,
    }
    assert second_report["proposed"] == {
        "account_balance_cents": 400000, "legacy_investment_cents": 0,
        "holding_value_cents": 1600000, "debt_balance_cents": 0,
        "net_worth_cents": 2000000,
    }
    first_source_report = next(
        row for row in second_report["sources"] if row["source"]["id"] == first_source["id"]
    )
    assert first_source_report["outcome"] == "converted"
    assert first_source_report["current_value_cents"] == 0
    assert first_source_report["current_holding_cents"] == 800000

    second_approval = client.post(
        ROOT + "/conversions/approvals",
        json=approval_body(second_preview, second_source["id"], second_account["id"], test_mode=True),
    )
    assert second_approval.status_code == 201, second_approval.text
    second_execution = client.post(
        ROOT + f"/conversions/{second_approval.json()['approval_id']}/execute",
        json={"idempotency_key": "second-batch-execution", "confirm_execute": True},
    )
    assert second_execution.status_code == 200, second_execution.text
    assert second_execution.json()["before_totals"] == second_report["current"]
    assert second_execution.json()["after_totals"] == second_report["proposed"]

    reversed_second = client.post(
        ROOT + f"/conversions/{second_approval.json()['approval_id']}/reverse",
        json={"reason": "Reverse latest disjoint test batch", "confirm_reverse": True},
    )
    assert reversed_second.status_code == 200, reversed_second.text
    assert reversed_second.json()["after_totals"] == second_report["current"]


@pytest.mark.parametrize("meaning", ["cash_only", "combined"])
def test_later_batch_requires_exact_prior_evidence_and_never_recorrects_holdings(
    client, db, monkeypatch, meaning,
):
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, source, preview = setup_report(client, symbol="BASE")
    approved = client.post(
        ROOT + "/conversions/approvals",
        json=approval_body(preview, source["id"], account["id"], test_mode=True),
    )
    assert approved.status_code == 201, approved.text
    executed = client.post(
        ROOT + f"/conversions/{approved.json()['approval_id']}/execute",
        json={"idempotency_key": "corrected-account-batch", "confirm_execute": True},
    )
    assert executed.status_code == 200, executed.text

    container_id = next(
        row["mapping"]["investment_account_id"]
        for row in preview["report"]["sources"]
        if row["source"]["id"] == source["id"]
    )
    instrument = create(client, "instruments", symbol="LATER", name="LATER", asset_type="STOCK")
    later_source = create(
        client, "investments", name="Later shares", ticker="LATER",
        quantity="10", cost_basis="1000", current_value="5000",
    )
    if meaning == "combined":
        create(client, f"accounts/{account['id']}/transactions",
               date="2026-01-01", transaction_type="Income", amount="5000",
               description="Synthetic ledger already includes newly mapped securities")
    draft = {
        "mappings": [{
            "source_id": later_source["id"], "investment_account_id": container_id,
            "instrument_id": instrument["id"], "specification_id": instrument["specification_id"],
            "identity_confirmed": True, "beneficial_ownership": "personal",
            "basis_status": "unverified",
        }],
        "accounts": [{
            "account_id": account["id"], "balance_meaning": meaning, "cash_cents": 200000,
            "evidence": "Later account statement", "complete": True,
            "source_ids": [later_source["id"]],
        }],
    }
    missing = client.post(ROOT + "/reconciliation/execution-preview", json=draft)
    assert missing.status_code == 200
    new_row = next(row for row in missing.json()["report"]["sources"]
                   if row["source"]["id"] == later_source["id"])
    assert new_row["outcome"] == "unresolved"
    assert client.post(ROOT + "/conversions/approvals", json=approval_body(
        missing.json(), later_source["id"], account["id"], test_mode=True,
    )).status_code == 422

    history_response = client.get(ROOT + "/conversions/review-context")
    assert history_response.headers["cache-control"] == "no-store"
    history = history_response.json()["accounts"][0]
    assert history["source_ids"] == [source["id"]]
    assert history["previous_correction_cents"] == -800000
    evidence = draft["accounts"][0]
    evidence.update(
        source_ids=[source["id"], later_source["id"]],
        prior_opening_position_ids=history["opening_position_ids"],
        prior_cash_entry_ids=history["cash_entry_ids"],
    )
    unchecked = client.post(ROOT + "/reconciliation/execution-preview", json=draft)
    assert next(row for row in unchecked.json()["report"]["sources"]
                if row["source"]["id"] == later_source["id"])["outcome"] == "unresolved"
    evidence["prior_conversion_complete"] = True
    reviewed = client.post(ROOT + "/reconciliation/execution-preview", json=draft)
    assert reviewed.status_code == 200, reviewed.text
    report = reviewed.json()["report"]
    correction = -500000 if meaning == "combined" else 0
    assert report["current"]["holding_value_cents"] == 800000
    assert report["proposed"]["holding_value_cents"] == 1300000
    assert report["proposed"]["account_balance_cents"] == 200000
    assert report["delta_cents"] == correction
    second_approval = client.post(ROOT + "/conversions/approvals", json=approval_body(
        reviewed.json(), later_source["id"], account["id"], test_mode=True,
    ))
    assert second_approval.status_code == 201, second_approval.text
    second_id = second_approval.json()["approval_id"]
    committed = client.post(ROOT + f"/conversions/{second_id}/execute", json={
        "idempotency_key": "later-attested-batch", "confirm_execute": True,
    })
    assert committed.status_code == 200, committed.text
    assert committed.json()["after_totals"] == report["proposed"]
    assert db.query(OpeningPosition).count() == 2
    assert db.query(CashReconciliationEntry).count() == (2 if meaning == "combined" else 1)
    assert client.get(ROOT + f"/accounts/{account['id']}").json()["cash_reconciliation_cents"] == (
        -800000 + correction
    )
    # A later conversion blocks the first; the new conversion can be reversed
    # without treating the earlier cash entry as newly applied or dependent.
    assert client.post(ROOT + f"/conversions/{approved.json()['approval_id']}/reverse",
                       json={"reason": "Unsafe earlier reversal", "confirm_reverse": True}).status_code == 409
    restored = client.post(ROOT + f"/conversions/{second_id}/reverse",
                           json={"reason": "Synthetic later batch reversal", "confirm_reverse": True})
    assert restored.status_code == 200, restored.text
    assert restored.json()["after_totals"] == report["current"]
    assert client.delete(ROOT + f"/investments/{later_source['id']}").status_code == 409
    assert client.get(ROOT + f"/investments/{later_source['id']}").json()["read_only"] is False

    evidence["prior_opening_position_ids"] = [999999]
    not_found = client.post(ROOT + "/reconciliation/execution-preview", json=draft)
    assert not_found.status_code == 404
    assert not_found.headers["cache-control"] == "no-store"


def test_injected_failure_after_ledger_writes_rolls_back_everything(
    client, db, monkeypatch,
):
    from services import conversion_service

    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    account, source, preview = setup_report(client)
    approved = client.post(ROOT + "/conversions/approvals", json=approval_body(
        preview, source["id"], account["id"], test_mode=True,
    ))
    assert approved.status_code == 201, approved.text
    approval_id = approved.json()["approval_id"]

    def fail_after_writes():
        raise RuntimeError("synthetic injected failure")

    monkeypatch.setattr(conversion_service, "_after_conversion_ledger_writes", fail_after_writes)
    response = client.post(ROOT + f"/conversions/{approval_id}/execute", json={
        "idempotency_key": "injected-failure-0001", "confirm_execute": True,
    })
    assert response.status_code == 503, response.text
    db.expire_all()
    approval = db.query(ReconciliationApproval).filter_by(id=approval_id).one()
    assert approval.state == "approved"
    assert approval.execution_idempotency_key is None
    assert db.query(OpeningPosition).count() == 0
    assert db.query(ValuationEligibility).count() == 0
    assert db.query(CashReconciliationEntry).count() == 0
    assert db.query(ConversionEvent).count() == 0


def test_foreign_owner_cannot_read_execute_or_reverse_approval(real_auth_client, monkeypatch):
    from conftest import sign_in_as

    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    sign_in_as(real_auth_client, "conversion-owner-a")
    account, source, preview = setup_report(real_auth_client)
    own_approval = real_auth_client.post(
        ROOT + "/conversions/approvals",
        json=approval_body(preview, source["id"], account["id"], test_mode=True),
    )
    assert own_approval.status_code == 201, own_approval.text
    approval_id = own_approval.json()["approval_id"]

    sign_in_as(real_auth_client, "conversion-owner-b")
    assert real_auth_client.get(ROOT + f"/conversions/{approval_id}").status_code == 404
    assert real_auth_client.get(ROOT + f"/conversions/{approval_id}/evidence").status_code == 404
    assert real_auth_client.post(ROOT + f"/conversions/{approval_id}/execute", json={
        "idempotency_key": "foreign-execution-key", "confirm_execute": True,
    }).status_code == 404
    assert real_auth_client.post(ROOT + f"/conversions/{approval_id}/reverse", json={
        "reason": "Foreign owner request", "confirm_reverse": True,
    }).status_code == 404


def test_sqlite_concurrent_execution_two_owners(client, monkeypatch, tmp_path):
    """Independent file connections prove actual commits, not a process mutex."""
    import threading
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from auth import require_session
    from main import app
    from schemas.conversion import ExecuteRequest
    from services import conversion_service
    from scripts.rehearse_database_restore import migrate_source
    from storage.database import get_db

    url = f"sqlite:///{tmp_path / 'disposable-conversion.db'}"
    migrate_source(url)
    engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 10})
    factory = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    owner = {"id": "sqlite-synthetic-owner-a"}

    def sessions():
        with factory() as session:
            yield session

    monkeypatch.setitem(app.dependency_overrides, get_db, sessions)
    monkeypatch.setitem(app.dependency_overrides, require_session, lambda: owner["id"])
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    monkeypatch.setenv("SERENITY_CONVERSION_SQLITE_TEST_DATABASE_URL", url)
    try:
        account_a, source_a, preview_a = setup_report(client, symbol="SQLA")
        approval_a = client.post(ROOT + "/conversions/approvals", json=approval_body(
            preview_a, source_a["id"], account_a["id"], test_mode=True,
        ))
        assert approval_a.status_code == 201, approval_a.text
        approval_id = approval_a.json()["approval_id"]
        later_preview = client.post(ROOT + "/reconciliation/execution-preview", json={
            "mappings": [row["mapping"] for row in preview_a["report"]["sources"]],
            "accounts": [row["evidence"] for row in preview_a["report"]["accounts"]],
        })
        assert later_preview.status_code == 200
        overlap = client.post(ROOT + "/conversions/approvals", json=approval_body(
            later_preview.json(), source_a["id"], account_a["id"], test_mode=True,
        ))
        assert overlap.status_code == 201, overlap.text
        overlap_id = overlap.json()["approval_id"]
        owner["id"] = "sqlite-synthetic-owner-b"
        account_b, source_b, preview_b = setup_report(client, symbol="SQLB")
        approval_b = client.post(ROOT + "/conversions/approvals", json=approval_body(
            preview_b, source_b["id"], account_b["id"], test_mode=True,
        ))
        assert approval_b.status_code == 201
        assert client.get(ROOT + "/conversions/review-context").json() == {"accounts": []}
        assert client.get(ROOT + f"/conversions/{approval_id}").status_code == 404
        entered, release = threading.Event(), threading.Event()
        results, conflicts, errors = [], [], []

        def pause():
            entered.set()
            assert release.wait(8)

        monkeypatch.setattr(conversion_service, "_after_conversion_ledger_writes", pause)

        def execute(approval, key, expect_conflict=False):
            try:
                with factory() as session:
                    result = conversion_service.execute(
                        session, "sqlite-synthetic-owner-a", "sqlite-synthetic-owner-a",
                        approval, ExecuteRequest(idempotency_key=key, confirm_execute=True),
                    )
                    assert not expect_conflict
                    results.append(result)
            except conversion_service.ConversionConflict as exc:
                (conflicts if expect_conflict else errors).append(exc)
            except BaseException as exc:
                errors.append(exc)

        first = threading.Thread(target=execute, args=(approval_id, "sqlite-execution-a"))
        duplicate = threading.Thread(target=execute, args=(approval_id, "sqlite-execution-a"))
        overlapping = threading.Thread(target=execute, args=(overlap_id, "sqlite-overlap-a", True))
        first.start()
        try:
            assert entered.wait(8)
            duplicate.start()
            overlapping.start()
        finally:
            release.set()
            for thread in (first, duplicate, overlapping):
                if thread.ident is not None:
                    thread.join(12)
        assert all(not thread.is_alive() for thread in (first, duplicate, overlapping))
        assert not errors
        assert len(results) == 2 and results[0] == results[1]
        assert len(conflicts) == 1
        with factory() as session:
            assert session.query(OpeningPosition).count() == 1
            assert session.query(CashReconciliationEntry).count() == 1
            assert session.query(ConversionEvent).count() == 1
            assert session.get(ReconciliationApproval, overlap_id).state == "approved"
        monkeypatch.setattr(conversion_service, "_after_conversion_ledger_writes", lambda: None)
        committed_b = client.post(
            ROOT + f"/conversions/{approval_b.json()['approval_id']}/execute",
            json={"idempotency_key": "sqlite-execution-b", "confirm_execute": True},
        )
        assert committed_b.status_code == 200, committed_b.text
        assert committed_b.json()["after_totals"] == preview_b["report"]["proposed"]
        assert client.get(ROOT + "/conversions/review-context").json()["accounts"][0]["source_ids"] == [source_b["id"]]
        assert client.get(ROOT + f"/conversions/{approval_id}/export").status_code == 404
        reversed_b = client.post(
            ROOT + f"/conversions/{approval_b.json()['approval_id']}/reverse",
            json={"reason": "Disposable owner B reversal", "confirm_reverse": True},
        )
        assert reversed_b.status_code == 200, reversed_b.text
        assert reversed_b.json()["after_totals"] == preview_b["report"]["current"]
    finally:
        engine.dispose()