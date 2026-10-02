from datetime import timedelta
from decimal import Decimal
import json

from models.account import Account, utc_now
from models.conversion import (
    CashReconciliationEntry,
    ConversionEvent,
    OpeningPosition,
    ReconciliationApproval,
    ValuationEligibility,
)
from models.instrument import Instrument, InstrumentSpecification
from models.investment import Investment
from services import account_service, dashboard_service, export_service, finance_service


def _converted_fixture(db, owner="test-owner"):
    account = Account(
        owner_id=owner, name="Brokerage", account_type="Investment",
        classification="Personal", opening_balance_cents=1_000_000,
    )
    db.add(account)
    source = Investment(
        owner_id=owner, name="Original shares", ticker="ABC", quantity_units=1000,
        cost_basis_cents=400_000, current_value_cents=800_000, active=True,
    )
    untouched = Investment(
        owner_id=owner, name="Legacy shares", ticker="XYZ", quantity_units=1000,
        cost_basis_cents=100_000, current_value_cents=50_000, active=True,
    )
    instrument = Instrument(owner_id=owner, symbol="ABC")
    db.add_all([source, untouched, instrument])
    db.flush()
    specification = InstrumentSpecification(
        owner_id=owner, instrument_id=instrument.id, version=1, symbol="ABC",
        name="ABC common stock", asset_type="stock", currency="USD",
        tick_size_units=1, point_value_units=1,
    )
    db.add(specification)
    db.flush()
    now = utc_now()
    approval = ReconciliationApproval(
        owner_id=owner, canonical_report=b"{}", report_format_version=1,
        algorithm_version="test", report_sha256="a" * 64, signed_token_evidence="test",
        preview_cutoff=now, source_fingerprint="test", approving_actor_id=owner,
        approved_source_ids=f"[{source.id}]", account_corrections_cents="{}",
        before_component_totals_cents="{}", after_component_totals_cents="{}",
        expected_delta_cents=-800_000, backup_evidence_reference="synthetic",
        backup_cutoff=now, rollback_deadline=now + timedelta(days=1),
    )
    db.add(approval)
    db.flush()
    opening = OpeningPosition(
        owner_id=owner, approval_id=approval.id, source_investment_id=source.id,
        cash_account_id=account.id,
        instrument_id=instrument.id, specification_id=specification.id,
        specification_version=1, quantity_units=source.quantity_units,
        entered_basis_cents=source.cost_basis_cents, basis_status="known",
        original_entered_value_cents=source.current_value_cents,
        source_snapshot='{"id":1}',
    )
    db.add(opening)
    db.flush()
    eligibility = ValuationEligibility(
            owner_id=owner, source_investment_id=source.id,
            opening_position_id=opening.id, approval_id=approval.id,
            representation="opening", status="active",
        )
    entry = CashReconciliationEntry(
            owner_id=owner, approval_id=approval.id, account_id=account.id,
            delta_cents=-800_000, reason="combined_balance_overlap",
            evidence="synthetic combined-balance overlap",
            before_balance_cents=1_000_000, after_balance_cents=200_000,
            actor_id=owner,
        )
    db.add_all([eligibility, entry])
    db.flush()
    db.add(ConversionEvent(
        owner_id=owner, approval_id=approval.id, event_kind="executed",
        before_totals="{}", after_totals="{}", source_account_state="{}",
        cutoff=now, actor_id=owner, report_sha256=approval.report_sha256,
        backup_evidence_reference="synthetic",
        linked_ids=json.dumps({
            "opening_position_ids": [opening.id],
            "cash_entry_ids": [entry.id],
            "source_ids": [source.id],
        }),
    ))
    db.commit()
    return account, source, untouched, opening


def test_conversion_selection_and_cash_correction_are_shared(db):
    account, source, untouched, opening = _converted_fixture(db)

    # Corrected cash is separate from Income/Expense; original source is
    # replaced by the opening value and the unlinked legacy value is unchanged.
    assert account_service.calculate_current_balance_cents(account, db) == 200_000
    assert account_service.get_account_totals(db, "test-owner").total_balance == Decimal("2000.00")
    assert finance_service.total_investment_value_cents(
        [source, untouched], db, "test-owner"
    ) == 850_000
    finance = finance_service.get_finance_summary(db, "test-owner")
    assert finance.investment_count == 2
    assert finance.investment_value == Decimal("8500.00")
    dashboard = dashboard_service.get_dashboard_summary(db, "test-owner")
    assert dashboard.net_worth == Decimal("10500.00")

    exported = export_service.build_export(db, "test-owner")
    assert exported["format_version"] == 7
    exported_account = exported["accounts"][0]
    assert exported_account["current_balance_cents"] == 200_000
    assert exported_account["current_balance"] == "2000.00"
    exported_sources = {row["id"]: row for row in exported["investments"]}
    assert exported_sources[source.id]["selected_for_valuation"] is False
    assert exported_sources[untouched.id]["selected_for_valuation"] is True
    assert exported["opening_positions"][0]["id"] == opening.id
    assert exported["opening_positions"][0]["selected_for_valuation"] is True
    assert len(exported["cash_reconciliation_entries"]) == 1
    assert exported["cash_reconciliation_entries"][0]["delta_cents"] == -800_000


def test_export_does_not_select_review_pending_investments(db):
    draft = Investment(
        owner_id="test-owner", name="Unreviewed shares", ticker="DRAFT",
        quantity_units=1250, cost_basis_cents=12_345,
        current_value_cents=23_456, review_pending=True,
    )
    db.add(draft)
    db.commit()

    exported = export_service.build_export(db, "test-owner")

    draft_export = next(row for row in exported["investments"] if row["id"] == draft.id)
    assert draft_export["selected_for_valuation"] is False
    assert draft_export["quantity_units"] == 1250
    assert draft_export["cost_basis_cents"] == 12_345
    assert draft_export["current_value_cents"] == 23_456


def test_conversion_export_references_are_owner_closed(db):
    _converted_fixture(db, "owner-a")
    _converted_fixture(db, "owner-b")

    for owner in ("owner-a", "owner-b"):
        exported = export_service.build_export(db, owner)
        investment_ids = {row["id"] for row in exported["investments"]}
        account_ids = {row["id"] for row in exported["accounts"]}
        approval_ids = {row["id"] for row in exported["reconciliation_approvals"]}
        opening_by_id = {row["id"]: row for row in exported["opening_positions"]}
        instrument_ids = {row["id"] for row in exported["instruments"]}
        specification_by_id = {
            row["id"]: row for row in exported["instrument_specifications"]
        }

        assert len(exported["investments"]) == 2
        assert len(exported["accounts"]) == 1
        for opening in opening_by_id.values():
            assert opening["approval_id"] in approval_ids
            assert opening["source_investment_id"] in investment_ids
            assert opening["cash_account_id"] in account_ids
            assert opening["instrument_id"] in instrument_ids
            assert opening["specification_id"] in specification_by_id
            assert specification_by_id[opening["specification_id"]]["instrument_id"] == opening["instrument_id"]
        for eligibility in exported["valuation_eligibility"]:
            assert eligibility["source_investment_id"] in investment_ids
            assert eligibility["opening_position_id"] in opening_by_id
            assert eligibility["approval_id"] in approval_ids
        for entry in exported["cash_reconciliation_entries"]:
            assert entry["approval_id"] in approval_ids
            assert entry["account_id"] in account_ids
            if entry["original_entry_id"] is not None:
                assert entry["original_entry_id"] in {
                    row["id"] for row in exported["cash_reconciliation_entries"]
                }
        for event in exported["conversion_events"]:
            assert event["approval_id"] in approval_ids
            links = json.loads(event["linked_ids"])
            assert set(links["opening_position_ids"]) <= set(opening_by_id)
            assert set(links["cash_entry_ids"]) <= {
                row["id"] for row in exported["cash_reconciliation_entries"]
            }
            assert set(links["source_ids"]) <= investment_ids


def test_converted_original_legacy_crud_is_read_only(client, db):
    _, source, _, _ = _converted_fixture(db)
    root = f"/serenity-api/investments/{source.id}"
    payload = {
        "name": "Edited", "ticker": "ABC", "quantity": 1,
        "cost_basis": 4000, "current_value": 8000,
    }
    assert client.put(root, json=payload).status_code == 409
    assert client.delete(root).status_code == 409
    assert client.post(root + "/deactivate").status_code == 409
    assert client.post(root + "/reactivate").status_code == 409

    # The legacy read route remains available as a historical source view.
    assert client.get(root).status_code == 200
    assert db.get(Investment, source.id).current_value_cents == 800_000