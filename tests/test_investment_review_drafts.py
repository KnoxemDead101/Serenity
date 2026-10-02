"""Assigned drafts stay uncounted until review; tests never use live records."""

from test_reconciliation_api import create, evidence, mapping, post_preview
from models.portfolio import InvestmentAccount, Portfolio
from models.account import Account
from services.dashboard_service import get_dashboard_summary


ROOT = "/serenity-api"


def test_assigned_draft_does_not_change_totals_and_review_is_explicit(client, db):
    account = create(client, "accounts", name="Brokerage", account_type="Brokerage",
                     classification="Personal", opening_balance="8000")
    portfolio = create(client, "portfolios", name="Long term")
    container = create(client, "investment-accounts", name="Brokerage sleeve",
                       portfolio_id=portfolio["id"], account_id=account["id"])
    instrument = create(client, "instruments", symbol="VTI", name="Fund", asset_type="ETF")
    before = get_dashboard_summary(db, "test-owner")
    draft = create(client, "investments", name="VTI shares", ticker="VTI",
                   quantity="10", cost_basis="6000", current_value="8000",
                   investment_account_id=container["id"])
    assert draft["review_pending"] is True
    assert draft["investment_account_id"] == container["id"]
    assert get_dashboard_summary(db, "test-owner") == before
    exported = client.get(ROOT + "/export").json()
    assert exported["format_version"] == 7
    assert exported["investments"][0]["review_pending"] is True
    assert exported["investments"][0]["investment_account_id"] == container["id"]
    unresolved = post_preview(client)["report"]
    assert unresolved["current"]["legacy_investment_cents"] == 0
    assert unresolved["proposed"]["holding_value_cents"] == 0
    assert unresolved["sources"][0]["outcome"] == "unresolved"

    reviewed = post_preview(client, [mapping(draft, container, instrument)],
                            [evidence(account, draft, meaning="combined", cash=0)])["report"]
    assert reviewed["sources"][0]["outcome"] == "eligible"
    assert reviewed["current"]["net_worth_cents"] == 800000
    assert reviewed["proposed"]["net_worth_cents"] == 800000
    assert reviewed["accounts"][0]["correction_cents"] == -800000
    assert get_dashboard_summary(db, "test-owner") == before  # preview writes nothing


def test_draft_cannot_target_another_owner_or_move_without_review(client, db):
    own = create(client, "accounts", name="Own", account_type="Brokerage",
                 classification="Personal", opening_balance="0")
    portfolio = create(client, "portfolios", name="Own")
    container = create(client, "investment-accounts", name="Own sleeve",
                       portfolio_id=portfolio["id"], account_id=own["id"])
    payload = {"name": "Stock", "quantity": "1", "cost_basis": "5",
               "current_value": "10", "investment_account_id": container["id"]}
    assert client.post(ROOT + "/investments", json={**payload, "investment_account_id": 99999}).status_code == 404
    db.add_all([
        Account(id=90001, owner_id="another-owner", name="Private cash",
                account_type="Brokerage", classification="Personal", opening_balance_cents=0),
        Portfolio(id=90001, owner_id="another-owner", name="Private portfolio"),
    ])
    db.flush()
    db.add(InvestmentAccount(id=90001, owner_id="another-owner", name="Private sleeve",
                             portfolio_id=90001, account_id=90001))
    db.commit()
    assert client.post(ROOT + "/investments", json={
        **payload, "investment_account_id": 90001}).status_code == 404
    foreign_portfolio = create(client, "portfolios", name="Archive me")
    foreign_container = create(client, "investment-accounts", name="Second",
                               portfolio_id=foreign_portfolio["id"],
                               account_id=create(client, "accounts", name="Other account",
                                                 account_type="Brokerage", classification="Personal",
                                                 opening_balance="0")["id"])
    assert client.post(ROOT + f"/investment-accounts/{foreign_container['id']}/deactivate").status_code == 200
    assert client.post(ROOT + "/investments", json={
        **payload, "investment_account_id": foreign_container["id"]}).status_code == 404
    draft = create(client, "investments", **payload)
    assert client.put(ROOT + f"/investments/{draft['id']}", json={
        **payload, "investment_account_id": foreign_container["id"]}).status_code == 409
    assert client.get(ROOT + f"/investments/{draft['id']}").json()["investment_account_id"] == container["id"]


def test_portfolio_first_draft_needs_no_container_and_account_is_reviewed_later(client, db):
    portfolio = create(client, "portfolios", name="Retirement")
    draft = create(client, "investments", name="Index shares", ticker="VTI",
                   quantity="2", cost_basis="80", current_value="100",
                   portfolio_id=portfolio["id"])
    assert draft["review_pending"] is True
    assert draft["portfolio_id"] == portfolio["id"]
    assert draft["investment_account_id"] is None
    assert get_dashboard_summary(db, "test-owner").net_worth == 0
    assert client.get(ROOT + "/export").json()["investments"][0]["portfolio_id"] == portfolio["id"]
    assert post_preview(client)["report"]["sources"][0]["outcome"] == "unresolved"

    account = create(client, "accounts", name="Cash ledger", account_type="Brokerage",
                     classification="Personal", opening_balance="100")
    instrument = create(client, "instruments", symbol="VTI", name="Index", asset_type="ETF")
    direct_mapping = {
        "source_id": draft["id"], "portfolio_id": portfolio["id"],
        "account_id": account["id"], "instrument_id": instrument["id"],
        "specification_id": instrument["specification_id"], "identity_confirmed": True,
        "beneficial_ownership": "personal", "basis_status": "unverified",
    }
    report = post_preview(client, [direct_mapping], [
        evidence(account, draft, meaning="combined", cash=0),
    ])["report"]
    assert report["sources"][0]["outcome"] == "eligible"
    assert report["current"]["net_worth_cents"] == 10000
    assert report["proposed"]["net_worth_cents"] == 10000
    assert get_dashboard_summary(db, "test-owner").net_worth == 100
    assert client.post(ROOT + f"/portfolios/{portfolio['id']}/deactivate").status_code == 409
    assert client.post(ROOT + "/investments", json={
        "name": "Foreign", "quantity": "1", "cost_basis": "1",
        "current_value": "1", "portfolio_id": 99999,
    }).status_code == 404
    other = create(client, "portfolios", name="Other")
    changed = client.put(ROOT + f"/investments/{draft['id']}", json={
        "name": "Index shares", "ticker": "VTI", "quantity": "2", "cost_basis": "80",
        "current_value": "100", "portfolio_id": other["id"],
    })
    assert changed.status_code == 200
    assert changed.json()["review_pending"] is True
    assert changed.json()["portfolio_id"] == other["id"]


def test_existing_investment_can_be_organized_without_reclassification(client, db):
    source = create(client, "investments", name="Earlier holding", ticker="VTI",
                    quantity="1", cost_basis="80", current_value="100")
    before = get_dashboard_summary(db, "test-owner")
    portfolio = create(client, "portfolios", name="Long-term")
    changed = client.put(ROOT + f"/investments/{source['id']}", json={
        "name": "Earlier holding", "ticker": "VTI", "quantity": "1",
        "cost_basis": "80", "current_value": "100", "portfolio_id": portfolio["id"],
    })
    assert changed.status_code == 200, changed.text
    assert changed.json()["portfolio_id"] == portfolio["id"]
    assert changed.json()["review_pending"] is False
    assert get_dashboard_summary(db, "test-owner") == before
    assert client.post(ROOT + f"/portfolios/{portfolio['id']}/deactivate").status_code == 409