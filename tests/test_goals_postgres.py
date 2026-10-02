"""Goal Core PostgreSQL coverage uses only the existing disposable cluster."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401
from tests.migration_helpers import current_head
from utils.choices import GOAL_PROGRESS_SOURCES


def test_goals_round_trip_large_bigint_and_have_owner_only_postgres_constraints(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "head")
    inspector = inspect(pg_engine)
    assert "goals" in inspector.get_table_names()

    columns = {column["name"]: column for column in inspector.get_columns("goals")}
    assert columns["target_amount_cents"]["type"].__class__.__name__ == "BIGINT"
    assert (
        columns["current_progress_amount_cents"]["type"].__class__.__name__
        == "BIGINT"
    )
    assert columns["owner_id"]["nullable"] is False
    assert inspector.get_foreign_keys("goals") == []
    assert any(
        index["name"] == "ix_goals_owner_id"
        and index["column_names"] == ["owner_id"]
        for index in inspector.get_indexes("goals")
    )
    assert any(
        constraint["name"] == "uq_goals_owner_id_id"
        and constraint["column_names"] == ["owner_id", "id"]
        for constraint in inspector.get_unique_constraints("goals")
    )

    created = pg_client.post("/serenity-api/goals", json={
        "name": "Large PostgreSQL goal",
        "description": None,
        "goal_type": "INVESTMENT",
        "category": "INVESTING",
        "target_date": None,
        "target_amount": "1000000000000.00",
        "current_progress_amount": "21474836.48",
        "progress_source": "MANUAL",
        "priority": "HIGH",
        "notes": None,
    })
    assert created.status_code == 201, created.text
    goal = created.json()
    assert goal["target_amount"] == "1000000000000.00"
    assert goal["target_amount_cents"] == 100_000_000_000_000
    assert goal["current_progress_amount"] == "21474836.48"
    assert goal["current_progress_amount_cents"] == 2_147_483_648

    with pg_engine.connect() as connection:
        row = connection.execute(text(
            "SELECT owner_id, target_amount_cents, current_progress_amount_cents "
            "FROM goals WHERE id = :id"
        ), {"id": goal["id"]}).one()
        assert tuple(row) == (
            "postgres-money-test", 100_000_000_000_000, 2_147_483_648,
        )
    exported = pg_client.get("/serenity-api/export")
    assert exported.status_code == 200, exported.text
    assert exported.json()["format_version"] == 7
    assert exported.json()["goals"][0]["target_amount"] == "1000000000000.00"

    refused = _alembic(
        postgres_url, "downgrade", "0017_portfolio_holdings", succeeds=False,
    )
    assert "Cannot downgrade Goal Core" in refused.stderr
    with pg_engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT version_num FROM alembic_version"
        )) == current_head()
        assert connection.scalar(text(
            "SELECT target_amount_cents FROM goals WHERE id = :id"
        ), {"id": goal["id"]}) == 100_000_000_000_000

        connection.execute(text("DELETE FROM goals"))
        connection.commit()

    _alembic(postgres_url, "downgrade", "0017_portfolio_holdings")
    with pg_engine.connect() as connection:
        assert set(connection.execute(text(
            "SELECT version_num FROM alembic_version"
        )).scalars()) == {
            "0017_conversion_guards", "0017_portfolio_holdings",
        }
    assert "goals" not in inspect(pg_engine).get_table_names()


PROGRESS_INSERT = text(
    "INSERT INTO goals (owner_id, name, goal_type, category, progress_source, "
    "current_progress_amount_cents, active, created_at, updated_at) "
    "VALUES ('postgres-money-test', 'Progress safeguard', 'SAVINGS', 'FINANCIAL', "
    ":source, :amount, :active, now(), now()) RETURNING id"
)


def test_postgres_raw_progress_inserts_and_updates(postgres_url, pg_engine):
    _alembic(postgres_url, "upgrade", "head")
    assert "ck_goals_manual_progress_only" in {
        check["name"] for check in inspect(pg_engine).get_check_constraints("goals")
    }
    with pg_engine.connect() as connection:
        for source in GOAL_PROGRESS_SOURCES:
            for amount in (None, 0, 12345, 100_000_000_000_000):
                for active in (True, False):
                    parameters = {"source": source, "amount": amount, "active": active}
                    if source == "MANUAL" or amount is None:
                        goal_id = connection.scalar(PROGRESS_INSERT, parameters)
                        assert tuple(connection.execute(text(
                            "SELECT progress_source, current_progress_amount_cents, active "
                            "FROM goals WHERE id = :id"
                        ), {"id": goal_id}).one()) == (source, amount, active)
                    else:
                        with pytest.raises(IntegrityError, match="ck_goals_manual_progress_only"):
                            with connection.begin_nested():
                                connection.execute(PROGRESS_INSERT, parameters)
                        goal_id = connection.scalar(
                            PROGRESS_INSERT, {**parameters, "source": "MANUAL"},
                        )
                        with pytest.raises(IntegrityError, match="ck_goals_manual_progress_only"):
                            with connection.begin_nested():
                                connection.execute(text(
                                    "UPDATE goals SET progress_source = :source WHERE id = :id"
                                ), {"source": source, "id": goal_id})
                        connection.execute(text(
                            "UPDATE goals SET progress_source = :source, "
                            "current_progress_amount_cents = NULL WHERE id = :id"
                        ), {"source": source, "id": goal_id})
                        with pytest.raises(IntegrityError, match="ck_goals_manual_progress_only"):
                            with connection.begin_nested():
                                connection.execute(text(
                                    "UPDATE goals SET current_progress_amount_cents = :amount "
                                    "WHERE id = :id"
                                ), {"amount": amount, "id": goal_id})
        connection.rollback()


def test_postgres_progress_upgrade_refuses_conflicts_and_preserves_rows(
    postgres_url, pg_engine,
):
    _alembic(postgres_url, "upgrade", "head")
    _alembic(postgres_url, "downgrade", "0022_publish_key_stage")
    with pg_engine.begin() as connection:
        for amount in (0, 12345):
            for active in (True, False):
                connection.execute(PROGRESS_INSERT, {
                    "source": "ACCOUNT_BALANCE", "amount": amount, "active": active,
                })
        before = connection.execute(text("SELECT * FROM goals ORDER BY id")).all()
    refused = _alembic(postgres_url, "upgrade", "head", succeeds=False)
    assert "preserve records and obtain explicit owner review" in refused.stderr
    with pg_engine.begin() as connection:
        assert connection.execute(text("SELECT * FROM goals ORDER BY id")).all() == before
        assert connection.scalar(text(
            "SELECT version_num FROM alembic_version"
        )) == "0022_publish_key_stage"
        # Remove only synthetic rows in this private disposable test cluster.
        connection.execute(text("DELETE FROM goals"))
        for source, amount in (("MANUAL", 0), ("MANUAL", 12345), ("ACCOUNT_BALANCE", None)):
            connection.execute(PROGRESS_INSERT, {
                "source": source, "amount": amount, "active": False,
            })
        before = connection.execute(text("SELECT * FROM goals ORDER BY id")).all()
    for command in (
        ("upgrade", "head"), ("downgrade", "0022_publish_key_stage"), ("upgrade", "head"),
    ):
        _alembic(postgres_url, *command)
        with pg_engine.connect() as connection:
            assert connection.execute(text("SELECT * FROM goals ORDER BY id")).all() == before
    with pg_engine.begin() as connection:
        connection.execute(text("DELETE FROM goals"))