"""Reconciliation is a read-only, owner-scoped snapshot on disposable PostgreSQL."""

import json

from sqlalchemy import text

from auth import require_session
from main import app
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401
from test_reconciliation_api import (
    create, evidence, mapping, post_preview, verify, without_export_time,
)


def test_postgres_exact_cents_read_only_and_stale_token(postgres_url, pg_engine, pg_client):
    _alembic(postgres_url, "upgrade", "head")
    owner = "postgres-money-test"
    account = create(pg_client, "accounts", name="Combined", account_type="Brokerage",
                     classification="Personal", opening_balance="10000")
    portfolio = create(pg_client, "portfolios", name="Holdings")
    sleeve = create(pg_client, "investment-accounts", name="Sleeve",
                    portfolio_id=portfolio["id"], account_id=account["id"])
    instrument = create(pg_client, "instruments", name="Company", symbol="TEST",
                        asset_type="STOCK")
    source = create(pg_client, "investments", name="Source", ticker="TEST",
                    quantity="40", cost_basis="6000", current_value="8000")
    before_export = pg_client.get("/serenity-api/export").json()
    before_dashboard_response = pg_client.get("/serenity-api/dashboard/summary")
    assert before_dashboard_response.status_code == 200
    before_dashboard = before_dashboard_response.json()
    with pg_engine.connect() as connection:
        before = {
            name: connection.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in ("accounts", "investments", "transactions", "portfolios",
                         "investment_accounts", "instruments", "instrument_specifications")
        }
    preview = post_preview(pg_client, [mapping(source, sleeve, instrument)],
                           [evidence(account, source, "combined", 200000)])
    report = preview["report"]
    assert report["current"]["net_worth_cents"] == 1800000
    assert report["proposed"]["net_worth_cents"] == 1000000
    assert report["delta_cents"] == -800000
    assert verify(pg_client, preview["report_token"]).json()["stale"] is False
    assert json.loads(verify(pg_client, preview["report_token"], "export").content) == preview
    assert without_export_time(pg_client.get("/serenity-api/export").json()) == (
        without_export_time(before_export)
    )
    assert pg_client.get("/serenity-api/dashboard/summary").json() == before_dashboard
    with pg_engine.connect() as connection:
        assert {
            name: connection.scalar(text(f"SELECT count(*) FROM {name}"))
            for name in before
        } == before
        assert connection.scalar(text(
            "SELECT opening_balance_cents FROM accounts WHERE id=:id"
        ), {"id": account["id"]}) == 1000000
        assert connection.scalar(text(
            "SELECT current_value_cents FROM investments WHERE id=:id"
        ), {"id": source["id"]}) == 800000
    app.dependency_overrides[require_session] = lambda: "unrelated-owner"
    assert verify(pg_client, preview["report_token"]).status_code == 404
    assert pg_client.post("/serenity-api/reconciliation/preview", json={
        "mappings": [mapping(source, sleeve, instrument)],
    }).status_code == 404
    assert pg_client.post("/serenity-api/reconciliation/preview", json={
        "accounts": [evidence(account, source)],
    }).status_code == 404
    app.dependency_overrides[require_session] = lambda: owner
    create(pg_client, f"accounts/{account['id']}/transactions", date="2026-02-01",
           transaction_type="Expense", amount="0.01", description="Changed ledger")
    check = verify(pg_client, preview["report_token"])
    assert check.status_code == 200, check.text
    assert check.json()["stale"] is True
    assert verify(pg_client, preview["report_token"], "export").status_code == 409