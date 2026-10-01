"""PostgreSQL-only checks use the existing disposable, socket-only cluster."""

from threading import Event, Thread

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from schemas.portfolio import InvestmentAccountWrite
from services import portfolio_service

from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401


def test_concurrent_move_then_archive_cannot_reactivate_from_stale_parent(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "head")
    def create(path, data):
        response = pg_client.post("/serenity-api/" + path, json=data)
        assert response.status_code == 201, response.text
        return response.json()

    cash = create("accounts", {
        "name": "Cash", "account_type": "Brokerage",
        "classification": "Personal", "opening_balance": "50",
    })
    a = create("portfolios", {"name": "A"})
    b = create("portfolios", {"name": "B"})
    container = create("investment-accounts", {
        "name": "Sleeve", "account_id": cash["id"], "portfolio_id": a["id"],
    })
    assert pg_client.post(
        f"/serenity-api/investment-accounts/{container['id']}/deactivate"
    ).status_code == 200

    # The reactor session keeps a previously read ORM row in its identity map.
    # A second session moves the inactive container to B and archives B before
    # the first resumes. Without FOR UPDATE + populate_existing, reactivation
    # sees stale A, checks the wrong parent, and activates a child of archived B.
    preloaded = Event()
    moved_and_archived = Event()
    outcome = {}

    def reactivate():
        try:
            with Session(pg_engine) as db:
                old = portfolio_service.get_investment_account(
                    db, "postgres-money-test", container["id"]
                )
                assert old.portfolio_id == a["id"]
                preloaded.set()
                if not moved_and_archived.wait(timeout=15):
                    raise TimeoutError("Move/archive transaction did not complete")
                portfolio_service.set_investment_account_active(
                    db, "postgres-money-test", container["id"], True
                )
                outcome["status"] = "unexpected activation"
        except portfolio_service.ContainerConflict as exc:
            outcome["status"] = str(exc)
        except Exception as exc:
            outcome["error"] = exc
            preloaded.set()

    worker = Thread(target=reactivate, daemon=True)
    worker.start()
    try:
        assert preloaded.wait(timeout=15), "Reactivation session never loaded the row"
        with Session(pg_engine) as db:
            portfolio_service.update_investment_account(
                db, "postgres-money-test", container["id"],
                InvestmentAccountWrite(
                    name="Moved", portfolio_id=b["id"], account_id=cash["id"]
                ),
            )
            archived = portfolio_service.set_portfolio_active(
                db, "postgres-money-test", b["id"], False
            )
            assert archived.active is False
    finally:
        moved_and_archived.set()
        worker.join(timeout=15)
    assert not worker.is_alive(), "Reactivation session blocked indefinitely"
    assert "error" not in outcome, outcome
    assert outcome["status"] == "Portfolio is inactive", outcome
    with Session(pg_engine) as db:
        current = portfolio_service.get_investment_account(
            db, "postgres-money-test", container["id"]
        )
        assert current.portfolio_id == b["id"]
        assert current.active is False


def test_postgres_portfolio_constraints_and_safe_downgrade(postgres_url, pg_engine, pg_client):
    _alembic(postgres_url, "upgrade", "0014_instrument_registry")
    with pg_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO accounts (id, owner_id, name, account_type, classification, "
            "opening_balance_cents, active, created_at, updated_at) "
            "VALUES (91001, 'other-owner', 'Other cash', 'Brokerage', 'Personal', "
            "45678, true, now(), now())"
        ))
    _alembic(postgres_url, "upgrade", "head")
    assert {"portfolios", "investment_accounts"} <= set(inspect(pg_engine).get_table_names())
    created = pg_client.post("/serenity-api/accounts", json={
        "name": "Protected", "account_type": "Brokerage",
        "classification": "Personal", "opening_balance": "123.45",
    })
    assert created.status_code == 201, created.text
    cash = created.json()
    p = pg_client.post("/serenity-api/portfolios", json={"name": "Protected portfolio"})
    assert p.status_code == 201, p.text
    p = p.json()
    container = pg_client.post("/serenity-api/investment-accounts", json={
        "name": "Protected sleeve", "portfolio_id": p["id"], "account_id": cash["id"],
    })
    assert container.status_code == 201, container.text
    container = container.json()
    assert pg_client.post(f"/serenity-api/portfolios/{p['id']}/deactivate").status_code == 409
    with pg_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO portfolios (id, owner_id, name, active, created_at, updated_at) "
            "VALUES (91001, 'other-owner', 'Foreign portfolio', true, now(), now())"
        ))
    for portfolio_id, account_id in ((p["id"], 91001), (91001, cash["id"])):
        with pytest.raises(IntegrityError):
            with pg_engine.begin() as connection:
                connection.execute(text(
                    "INSERT INTO investment_accounts (owner_id, portfolio_id, account_id, "
                    "name, active, created_at, updated_at) "
                    "VALUES ('postgres-money-test', :portfolio, :account, "
                    "'Wrong owner', true, now(), now())"
                ), {"portfolio": portfolio_id, "account": account_id})
    refused = _alembic(postgres_url, "downgrade", "0014_instrument_registry", succeeds=False)
    assert "Cannot downgrade 0015" in refused.stderr
    with pg_engine.connect() as connection:
        # PostgreSQL rolls back the whole failed downgrade transaction.
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0017_portfolio_holdings"
        assert connection.scalar(text("SELECT opening_balance_cents FROM accounts WHERE id = :id"),
                                 {"id": cash["id"]}) == 12345
    assert pg_client.post(f"/serenity-api/investment-accounts/{container['id']}/deactivate").status_code == 200
    with pg_engine.begin() as connection:
        connection.execute(text("DELETE FROM investment_accounts"))
        connection.execute(text("DELETE FROM portfolios"))
    _alembic(postgres_url, "downgrade", "0014_instrument_registry")
    with pg_engine.connect() as connection:
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == "0014_instrument_registry"
        assert connection.scalar(text("SELECT opening_balance_cents FROM accounts WHERE id = :id"),
                                 {"id": cash["id"]}) == 12345
        assert connection.scalar(text("SELECT opening_balance_cents FROM accounts WHERE id = 91001")) == 45678