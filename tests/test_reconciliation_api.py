"""Read-only reconciliation contracts against isolated in-memory SQLite owners."""

import json

import pytest
from auth import require_session
from main import app
from models.account import Account
from models.bill import Bill
from models.business import Business
from models.debt import Debt
from models.dependent import Dependent
from models.income_profile import IncomeProfile
from models.investment import Investment
from models.instrument import Instrument, InstrumentSpecification
from models.portfolio import InvestmentAccount, Portfolio
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from services.dashboard_service import get_dashboard_summary


ROOT = "/serenity-api"
TABLES = (Account, Bill, Business, Debt, Dependent, IncomeProfile, Investment,
          Instrument, InstrumentSpecification, Portfolio, InvestmentAccount,
          Transaction, TransactionCorrection)


def create(client, path, **fields):
    response = client.post(ROOT + "/" + path, json=fields)
    assert response.status_code == 201, response.text
    return response.json()


def post_preview(client, mappings=None, accounts=None):
    response = client.post(ROOT + "/reconciliation/preview", json={
        "mappings": mappings or [], "accounts": accounts or [],
    })
    assert response.status_code == 200, response.text
    result = response.json()
    assert isinstance(result["report_token"], str) and result["report_token"]
    return result


def verify(client, token, action="verify"):
    return client.post(ROOT + "/reconciliation/" + action,
                       json={"report_token": token})


def seed(client, balance="2000", value="8000", basis="6000", ticker="ACME"):
    account = create(client, "accounts", name="Brokerage", account_type="Brokerage",
                     classification="Personal", opening_balance=balance)
    portfolio = create(client, "portfolios", name="My investments")
    container = create(client, "investment-accounts", name="Brokerage sleeve",
                       portfolio_id=portfolio["id"], account_id=account["id"])
    instrument = create(client, "instruments", symbol=ticker, name="ACME",
                        asset_type="STOCK")
    source = create(client, "investments", name="Original shares", ticker=ticker,
                    quantity="40", cost_basis=basis, current_value=value,
                    notes="User's original entry")
    return account, portfolio, container, instrument, source


def mapping(source, container, instrument, **kwargs):
    return {
        "source_id": source["id"], "investment_account_id": container["id"],
        "instrument_id": instrument["id"],
        "specification_id": instrument["specification_id"],
        "identity_confirmed": True, "beneficial_ownership": "personal",
        "basis_status": "unverified", **kwargs,
    }


def evidence(account, source, meaning="cash_only", cash=200000, **kwargs):
    return {
        "account_id": account["id"], "balance_meaning": meaning,
        "cash_cents": cash, "evidence": "Reviewed synthetic account statement",
        "complete": True, "source_ids": [source["id"]], **kwargs,
    }


def rows_by_id(report, key):
    return {row["source"]["id"] if key == "sources" else row["account"]["id"]: row
            for row in report[key]}


def counts(db):
    db.expire_all()
    return {table.__tablename__: db.query(table).count() for table in TABLES}


def without_export_time(export):
    return {key: value for key, value in export.items() if key != "exported_at"}


@pytest.mark.parametrize("balance,meaning,cash,expected,delta", [
    ("2000", "cash_only", 200000, 1000000, 0),
    ("10000", "combined", 200000, 1000000, -800000),
])
def test_exact_cents_snapshot_and_no_postings(client, db, balance, meaning, cash,
                                               expected, delta):
    account, portfolio, container, instrument, source = seed(client, balance)
    before_summary = get_dashboard_summary(db, "test-owner")
    before_export = client.get(ROOT + "/export").json()
    before_counts = counts(db)
    original_investment = db.get(Investment, source["id"])
    original_fields = (original_investment.quantity_units,
                       original_investment.cost_basis_cents,
                       original_investment.current_value_cents,
                       original_investment.created_at, original_investment.updated_at)
    request_mapping = mapping(source, container, instrument)
    preview = post_preview(client, [request_mapping],
                           [evidence(account, source, meaning, cash)])
    report = preview["report"]
    assert report["format_version"]
    assert report["captured_at"]
    assert report["source_fingerprint"]
    assert report["current"]["net_worth_cents"] == int(balance) * 100 + 800000
    assert report["proposed"]["net_worth_cents"] == expected
    assert report["delta_cents"] == delta
    assert report["current"]["legacy_investment_cents"] == 800000
    assert report["proposed"]["legacy_investment_cents"] == 0
    assert report["proposed"]["holding_value_cents"] == 800000
    assert report["proposed"]["account_balance_cents"] == cash
    record = rows_by_id(report, "sources")[source["id"]]
    assert record["outcome"] == "eligible"
    assert record["source"]["ticker"] == "ACME"
    assert record["source"]["quantity_units"] == original_fields[0]
    assert record["source"]["cost_basis_cents"] == 600000
    assert record["source"]["current_value_cents"] == 800000
    assert record["source"]["notes"] == "User's original entry"
    assert record["basis_cents"] == 600000
    assert record["basis_status"] == "unverified"
    assert record["current_value_cents"] == 800000
    assert record["proposed_legacy_cents"] == 0
    assert record["proposed_holding_cents"] == 800000
    assert record["valuation"]["as_of"] is None
    assert rows_by_id(report, "accounts")[account["id"]]["correction_cents"] == delta
    if delta:
        assert report["explanations"]
    assert verify(client, preview["report_token"]).json() == {
        "valid": True, "stale": False, "report": report,
    }
    exported = verify(client, preview["report_token"], "export")
    assert exported.status_code == 200, exported.text
    assert "attachment" in exported.headers["content-disposition"].lower()
    assert json.loads(exported.content) == preview
    # Preview, verification, export and cancel (discard token) are all no-ops.
    assert counts(db) == before_counts
    db.expire_all()
    source_after = db.get(Investment, source["id"])
    assert (source_after.quantity_units, source_after.cost_basis_cents,
            source_after.current_value_cents, source_after.created_at,
            source_after.updated_at) == original_fields
    assert get_dashboard_summary(db, "test-owner") == before_summary
    assert without_export_time(client.get(ROOT + "/export").json()) == (
        without_export_time(before_export)
    )
    assert client.get(ROOT + "/export/transactions.csv").status_code == 200
    assert post_preview(client)["report"]["current"]["net_worth_cents"] == (
        int(balance) * 100 + 800000
    )


def test_partial_batch_unknown_account_blocks_group_and_never_double_counts(client):
    account, _, sleeve, instrument, first = seed(client, "15000")
    second = create(client, "investments", name="Other shares", ticker="ACME",
                    quantity="2", cost_basis="100", current_value="5000")
    declaration = evidence(account, first, "combined", 200000,
                           source_ids=[first["id"]])
    incomplete = post_preview(client, [mapping(first, sleeve, instrument)],
                              [declaration])["report"]
    assert rows_by_id(incomplete, "sources")[first["id"]]["outcome"] == "unresolved"
    assert incomplete["proposed"]["holding_value_cents"] == 0
    assert incomplete["delta_cents"] == 0
    partial = post_preview(client, [
        mapping(first, sleeve, instrument),
        mapping(second, sleeve, instrument, identity_confirmed=False),
    ], [evidence(account, first, "combined", 200000,
                source_ids=[first["id"], second["id"]])])["report"]
    assert rows_by_id(partial, "sources")[first["id"]]["outcome"] == "unresolved"
    assert rows_by_id(partial, "sources")[second["id"]]["outcome"] == "unresolved"
    assert partial["proposed"]["account_balance_cents"] == 1500000
    assert partial["proposed"]["holding_value_cents"] == 0
    unknown = post_preview(client, [mapping(first, sleeve, instrument)],
                           [evidence(account, first, "unknown", None,
                                     complete=False)])["report"]
    assert rows_by_id(unknown, "sources")[first["id"]]["outcome"] == "unresolved"
    assert unknown["delta_cents"] == 0


def test_inactive_zero_and_unknown_basis_and_dated_provenance(client):
    account, _, sleeve, instrument, first = seed(client)
    inactive = create(client, "investments", name="Inactive", quantity="1",
                      cost_basis="10", current_value="20")
    assert client.post(ROOT + f"/investments/{inactive['id']}/deactivate").status_code == 200
    zero = create(client, "investments", name="Zero entered basis", ticker="ACME",
                  quantity="1", cost_basis="0", current_value="100")
    report = post_preview(client, [
        mapping(first, sleeve, instrument, basis_status="unknown",
                valuation_as_of="2026-01-31", valuation_evidence="Archived statement"),
    ], [evidence(account, first)])["report"]
    rows = rows_by_id(report, "sources")
    assert rows[first["id"]]["outcome"] == "eligible"
    assert rows[first["id"]]["basis_status"] == "unknown"
    assert rows[first["id"]]["basis_cents"] is None
    assert rows[first["id"]]["source"]["cost_basis_cents"] == 600000
    assert rows[first["id"]]["valuation"]["as_of"] == "2026-01-31"
    assert rows[first["id"]]["valuation"]["evidence"] == "Archived statement"
    assert rows[first["id"]]["valuation"]["provenance"] == "legacy_user_entered"
    assert rows[zero["id"]]["outcome"] == "unresolved"
    assert rows[inactive["id"]]["outcome"] == "inactive"
    assert rows[inactive["id"]]["current_value_cents"] == 0
    assert rows[inactive["id"]]["proposed_holding_cents"] == 0
    assert report["delta_cents"] == 0
    zero_report = post_preview(client, [
        mapping(zero, sleeve, instrument),
    ], [evidence(account, zero)])["report"]
    assert rows_by_id(zero_report, "sources")[zero["id"]]["outcome"] == "unresolved"
    assert rows_by_id(zero_report, "sources")[zero["id"]]["warnings"]
    assert client.post(ROOT + "/reconciliation/preview", json={
        "mappings": [mapping(first, sleeve, instrument,
                             valuation_as_of="2026-01-31")],
    }).status_code == 422
    reviewed = post_preview(client, [
        mapping(zero, sleeve, instrument, zero_basis_reviewed=True),
    ], [evidence(account, zero, cash=200000)])["report"]
    assert rows_by_id(reviewed, "sources")[zero["id"]]["outcome"] == "eligible"
    assert rows_by_id(reviewed, "sources")[zero["id"]]["basis_cents"] == 0


def test_ambiguous_identity_requires_exact_spec_and_no_ticker_guess(client):
    account, _, sleeve, instrument, source = seed(client)
    second = create(client, "instruments", symbol="ANOTHER", name="Another",
                    asset_type="ETF")
    for partial in (
        {"instrument_id": None, "specification_id": None},
        {"instrument_id": instrument["id"], "specification_id": None},
        {"instrument_id": None, "specification_id": instrument["specification_id"]},
        {"identity_confirmed": False},
        {"beneficial_ownership": "simulation"},
        {"beneficial_ownership": "prop"},
    ):
        report = post_preview(client, [mapping(source, sleeve, instrument, **partial)],
                              [evidence(account, source)])["report"]
        assert rows_by_id(report, "sources")[source["id"]]["outcome"] == "unresolved"
        assert report["proposed"]["holding_value_cents"] == 0
    mismatch = client.post(ROOT + "/reconciliation/preview", json={
        "mappings": [mapping(source, sleeve, instrument,
                             specification_id=second["specification_id"])],
    })
    assert mismatch.status_code == 404


def test_two_owner_isolation_in_ids_reports_exports_and_unauthenticated(real_auth_client, db):
    from conftest import sign_in_as
    sign_in_as(real_auth_client, "owner-a")
    a, _, sleeve_a, instrument_a, source_a = seed(real_auth_client)
    own = post_preview(real_auth_client, [mapping(source_a, sleeve_a, instrument_a)],
                       [evidence(a, source_a)])
    sign_in_as(real_auth_client, "owner-b")
    b, _, sleeve_b, instrument_b, source_b = seed(real_auth_client, ticker="OTHER")
    own_b = post_preview(real_auth_client, [mapping(source_b, sleeve_b, instrument_b)],
                         [evidence(b, source_b)])
    for foreign_mapping in (
        mapping(source_a, sleeve_b, instrument_b),
        mapping(source_b, sleeve_a, instrument_b),
        mapping(source_b, sleeve_b, instrument_a),
        mapping(source_b, sleeve_b, instrument_b,
                specification_id=instrument_a["specification_id"]),
    ):
        response = real_auth_client.post(ROOT + "/reconciliation/preview", json={
            "mappings": [foreign_mapping],
        })
        assert response.status_code == 404, response.text
    assert real_auth_client.post(ROOT + "/reconciliation/preview", json={
        "accounts": [evidence(a, source_b)],
    }).status_code == 404
    assert real_auth_client.post(ROOT + "/reconciliation/preview", json={
        "accounts": [evidence(b, source_a)],
    }).status_code == 404
    assert verify(real_auth_client, own["report_token"]).status_code == 404
    assert verify(real_auth_client, own["report_token"], "export").status_code == 404
    assert verify(real_auth_client, own_b["report_token"]).json()["stale"] is False
    assert {row["source"]["id"] for row in own_b["report"]["sources"]} == {source_b["id"]}
    assert {row["account"]["id"] for row in own_b["report"]["accounts"]} == {b["id"]}
    assert source_a["id"] not in {row["source"]["id"] for row in own_b["report"]["sources"]}
    assert real_auth_client.get(ROOT + "/export").json()["investments"][0]["id"] == source_b["id"]
    real_auth_client.cookies.clear()
    for path in ("preview", "verify", "export"):
        assert real_auth_client.post(ROOT + "/reconciliation/" + path, json={
            "report_token": own_b["report_token"],
        }).status_code == 401


def test_duplicate_invalid_declarations_and_signed_tamper(client):
    account, _, sleeve, instrument, source = seed(client)
    m = mapping(source, sleeve, instrument)
    e = evidence(account, source)
    for mappings, accounts in (([m, m], [e]), ([m], [e, e]),
                               ([m], [{**e, "source_ids": [source["id"]] * 2}])):
        assert client.post(ROOT + "/reconciliation/preview", json={
            "mappings": mappings, "accounts": accounts,
        }).status_code == 422
    other_account = create(client, "accounts", name="Other ledger",
                           account_type="Brokerage", classification="Personal",
                           opening_balance="0")
    assert client.post(ROOT + "/reconciliation/preview", json={
        "mappings": [m],
        "accounts": [evidence(other_account, source)],
    }).status_code == 404
    token = post_preview(client, [m], [e])["report_token"]
    altered = token[:-1] + ("A" if token[-1] != "A" else "B")
    for action in ("verify", "export"):
        assert verify(client, altered, action).status_code == 404
        assert verify(client, "unsigned.synthetic.report", action).status_code == 404


def test_empty_preview_strict_cents_missing_secret_and_owner_independent_changes(
    client, monkeypatch,
):
    empty = post_preview(client)
    assert empty["report"]["sources"] == []
    assert empty["report"]["accounts"] == []
    assert empty["report"]["delta_cents"] == 0
    account, _, sleeve, instrument, source = seed(client)
    for invalid in (1.01, "200000", True):
        response = client.post(ROOT + "/reconciliation/preview", json={
            "mappings": [mapping(source, sleeve, instrument)],
            "accounts": [evidence(account, source, cash=invalid)],
        })
        assert response.status_code == 422, response.text
    valid = post_preview(client, [mapping(source, sleeve, instrument)],
                         [evidence(account, source)])
    monkeypatch.setenv("SESSION_SECRET", "rotated-test-only-secret")
    assert verify(client, valid["report_token"]).status_code == 404
    assert verify(client, valid["report_token"], "export").status_code == 404
    monkeypatch.delenv("SESSION_SECRET", raising=False)
    assert client.post(ROOT + "/reconciliation/preview", json={}).status_code == 503
    assert verify(client, valid["report_token"]).status_code == 503
    assert verify(client, valid["report_token"], "export").status_code == 503


@pytest.mark.parametrize("change", [
    "source", "account", "transaction", "portfolio", "membership", "container",
    "instrument", "debt",
])
def test_signed_snapshot_detects_financial_and_reference_changes(client, change):
    account, portfolio, sleeve, instrument, source = seed(client)
    debt = create(client, "debts", name="Card", balance="15",
                  minimum_payment="1")
    transaction = create(client, f"accounts/{account['id']}/transactions",
                         date="2026-01-10", transaction_type="Income",
                         amount="5", description="Deposit")
    preview = post_preview(client, [mapping(source, sleeve, instrument)],
                           [evidence(account, source, cash=200500)])
    assert verify(client, preview["report_token"]).json()["stale"] is False
    if change == "source":
        response = client.put(ROOT + f"/investments/{source['id']}", json={
            "name": "Edited", "ticker": "ACME", "quantity": "40",
            "cost_basis": "6000", "current_value": "8000.01",
        })
    elif change == "account":
        response = client.put(ROOT + f"/accounts/{account['id']}", json={
            "name": "Edited", "account_type": "Brokerage",
            "classification": "Personal", "opening_balance": "2000",
        })
    elif change == "transaction":
        response = client.post(ROOT + f"/accounts/{account['id']}/transactions", json={
            "date": "2026-02-01", "transaction_type": "Expense",
            "amount": "0.01", "description": "Additional posting",
        })
    elif change == "portfolio":
        response = client.put(ROOT + f"/portfolios/{portfolio['id']}", json={
            "name": "Changed parent",
        })
    elif change == "membership":
        new_parent = create(client, "portfolios", name="Replacement parent")
        response = client.put(ROOT + f"/investment-accounts/{sleeve['id']}", json={
            "name": "Sleeve", "portfolio_id": new_parent["id"],
            "account_id": account["id"],
        })
    elif change == "container":
        response = client.post(ROOT + f"/investment-accounts/{sleeve['id']}/deactivate")
    elif change == "instrument":
        response = client.post(ROOT + f"/instruments/{instrument['id']}/deactivate")
    else:
        response = client.post(ROOT + f"/debts/{debt['id']}/deactivate")
    assert response.status_code in (200, 201), response.text
    checked = verify(client, preview["report_token"])
    assert checked.status_code == 200, checked.text
    assert checked.json()["valid"] is True
    assert checked.json()["stale"] is True
    assert checked.json()["report"] == preview["report"]
    assert verify(client, preview["report_token"], "export").status_code == 409