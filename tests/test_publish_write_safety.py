"""Staging, service/API write refusal, and restoration on a private PG cluster."""

import pytest
import json
from pathlib import Path
from sqlalchemy import delete, inspect, text
from sqlalchemy.orm import Session

from migrations.publish_key_references import REFERENCES
from models.account import Account
from schemas.portfolio import PortfolioWrite
from services import portfolio_service
from services.write_safety import MESSAGE, WritesPaused, write_state
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401


@pytest.fixture(autouse=True)
def fresh_staging_schema(postgres_url, pg_engine):
    # Imported PostgreSQL fixtures share one disposable cluster per module.
    # These tests intentionally damage schema, so start each on an empty schema.
    # Refuse any target except the fixture's private Unix-socket cluster.
    assert postgres_url.startswith("postgresql://moneytest@/postgres?host=/tmp/")
    assert "/isolated-money-pg" in postgres_url and "/socket" in postgres_url
    with pg_engine.begin() as connection:
        connection.exec_driver_sql("DROP SCHEMA public CASCADE")
        connection.exec_driver_sql("CREATE SCHEMA public")


def test_staging_preserves_records_blocks_writes_and_restores(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "0021_publish_parent_keys")
    with pg_engine.begin() as connection:
        account_id = connection.scalar(text(
            "INSERT INTO accounts (owner_id, name, account_type, classification, "
            "opening_balance_cents, active, created_at, updated_at) VALUES "
            "('postgres-money-test', 'Protected synthetic cash', 'Checking', "
            "'Personal', 54321, true, now(), now()) RETURNING id"
        ))
        before = connection.scalar(text(
            "SELECT row_to_json(a)::text FROM accounts a WHERE id=:id"
        ), {"id": account_id})
        assert write_state(connection) == "NORMAL"
    _alembic(postgres_url, "upgrade", "0022_publish_key_stage")
    with pg_engine.connect() as connection:
        assert write_state(connection) == "READ_ONLY"
        assert connection.scalar(text(
            "SELECT row_to_json(a)::text FROM accounts a WHERE id=:id"
        ), {"id": account_id}) == before
        names = set(connection.execute(text(
            "SELECT conname FROM pg_constraint WHERE contype='f'"
        )).scalars())
        assert not names.intersection(item[1] for item in REFERENCES)
        assert "fk_opening_positions_owner_approval" in names

    status = pg_client.get("/serenity-api/system/write-safety")
    assert status.status_code == 200
    assert status.json()["state"] == "READ_ONLY"
    assert status.headers["cache-control"] == "no-store"
    for method, path, payload in (
        ("POST", "/serenity-api/portfolios", {"name": "Blocked"}),
        ("POST", f"/serenity-api/accounts/{account_id}/deactivate", {}),
        ("PUT", f"/serenity-api/accounts/{account_id}", {"name": "Blocked"}),
        ("POST", "/serenity-api/conversions/approvals", {}),
        ("POST", "/serenity-api/goals", {}),
    ):
        response = pg_client.request(method, path, json=payload)
        assert response.status_code == 503, response.text
        assert response.json()["detail"] == MESSAGE
    assert pg_client.get("/serenity-api/accounts").status_code == 200

    with Session(pg_engine) as db:
        with pytest.raises(WritesPaused):
            portfolio_service.create_portfolio(
                db, "postgres-money-test", PortfolioWrite(name="Blocked direct service"),
            )
        db.rollback()
        row = db.get(Account, account_id)
        row.opening_balance_cents = 1
        with pytest.raises(WritesPaused):
            db.commit()
        db.rollback()
        with pytest.raises(WritesPaused):
            db.execute(delete(Account).where(Account.id == account_id))
        db.rollback()

    _alembic(postgres_url, "downgrade", "0021_publish_parent_keys")
    with pg_engine.connect() as connection:
        assert write_state(connection) == "NORMAL"
        assert connection.scalar(text(
            "SELECT row_to_json(a)::text FROM accounts a WHERE id=:id"
        ), {"id": account_id}) == before
    assert pg_client.get("/serenity-api/system/write-safety").json()["writes_enabled"]
    assert pg_client.post(
        "/serenity-api/portfolios", json={"name": "After restoration"},
    ).status_code == 201


@pytest.mark.parametrize("unsafe", ["wrong_target", "not_valid"])
def test_present_but_unsafe_constraint_cannot_unlock_writes(
    postgres_url, pg_engine, unsafe,
):
    _alembic(postgres_url, "upgrade", "0021_publish_parent_keys")
    with pg_engine.begin() as connection:
        assert write_state(connection) == "NORMAL"
        connection.execute(text(
            "ALTER TABLE opening_positions "
            "DROP CONSTRAINT fk_opening_positions_owner_account"
        ))
        target = "investments" if unsafe == "wrong_target" else "accounts"
        validation = " NOT VALID" if unsafe == "not_valid" else ""
        connection.execute(text(
            "ALTER TABLE opening_positions "
            "ADD CONSTRAINT fk_opening_positions_owner_account "
            f"FOREIGN KEY (owner_id,cash_account_id) REFERENCES {target}(owner_id,id) "
            f"ON DELETE RESTRICT{validation}"
        ))
        # Constraint names can repeat between tables. A validated namesake
        # must not make the unvalidated opening-position key look safe.
        connection.execute(text(
            "ALTER TABLE investment_accounts "
            "ADD CONSTRAINT fk_opening_positions_owner_account "
            "FOREIGN KEY (owner_id,account_id) REFERENCES accounts(owner_id,id) "
            "ON DELETE RESTRICT"
        ))
        assert write_state(connection) == "READ_ONLY"


def test_exact_first_publish_plan_replays_without_reordering(
    postgres_url, pg_engine,
):
    plan = json.loads((Path(__file__).parent / "fixtures" /
                       "publish_stage1_schema_diff.json").read_text())
    assert plan["success"] and not plan["hasStructuralDataLoss"]
    assert not plan["tablesToRemove"] and not plan["columnsToRemove"]
    _alembic(postgres_url, "upgrade", "0014_instrument_registry")
    with pg_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO accounts (owner_id,name,account_type,classification,"
            "opening_balance_cents,active,created_at,updated_at) VALUES "
            "('publish-replay','Synthetic prior record','Checking','Personal',"
            "76543,true,now(),now())"
        ))
        before = connection.execute(text(
            "SELECT row_to_json(a)::text FROM accounts a ORDER BY id"
        )).scalars().all()
        for number, statement in enumerate(plan["statementsToExecute"], 1):
            try:
                connection.exec_driver_sql(statement)
            except Exception as error:
                raise AssertionError(f"Publish statement {number} failed") from error
        assert write_state(connection) == "READ_ONLY"
        assert connection.execute(text(
            "SELECT row_to_json(a)::text FROM accounts a ORDER BY id"
        )).scalars().all() == before
        for table, columns in (
            ("accounts", ("owner_id", "id")),
            ("investments", ("owner_id", "id")),
            ("instruments", ("owner_id", "id")),
            ("instrument_specifications", ("owner_id", "instrument_id", "id")),
        ):
            assert connection.scalar(text(
                "SELECT count(*) FROM pg_constraint WHERE contype='u' "
                "AND conrelid=to_regclass(:table) AND conname=:name"
            ), {"table": table, "name": f"uq_{table}_{'_'.join(columns)}"}) == 1


def test_forward_restoration_preserves_records_and_keeps_keys_on_downgrade(
    postgres_url, pg_engine,
):
    _alembic(postgres_url, "upgrade", "0023_goal_progress_guard")
    with pg_engine.begin() as connection:
        assert write_state(connection) == "READ_ONLY"
        connection.execute(text(
            "INSERT INTO accounts (owner_id,name,account_type,classification,"
            "opening_balance_cents,active,created_at,updated_at) VALUES "
            "('restoration-test','Synthetic prior account','Checking','Personal',"
            "12345,true,now(),now())"
        ))
        before = connection.execute(text(
            "SELECT row_to_json(a)::text FROM accounts a ORDER BY id"
        )).scalars().all()
    _alembic(postgres_url, "upgrade", "0024_restore_publish_keys")
    with pg_engine.connect() as connection:
        assert write_state(connection) == "NORMAL"
        assert connection.execute(text(
            "SELECT row_to_json(a)::text FROM accounts a ORDER BY id"
        )).scalars().all() == before
    _alembic(postgres_url, "downgrade", "0023_goal_progress_guard")
    with pg_engine.connect() as connection:
        assert write_state(connection) == "NORMAL"


def test_exact_second_publish_plan_preserves_rows_and_restores_valid_keys(
    postgres_url, pg_engine,
):
    fixtures = Path(__file__).parent / "fixtures"
    first = json.loads((fixtures / "publish_stage1_schema_diff.json").read_text())
    second = json.loads((fixtures / "publish_stage2_schema_diff.json").read_text())
    assert second["success"] and not second["hasStructuralDataLoss"]
    assert not second["warnings"]
    for field in (
        "tablesToRemove", "tablesToTruncate", "columnsToRemove",
        "schemasToRemove", "matViewsToRemove",
    ):
        assert not second[field]
    assert len(second["statementsToExecute"]) == 12
    _alembic(postgres_url, "upgrade", "0014_instrument_registry")
    with pg_engine.begin() as connection:
        for statement in first["statementsToExecute"]:
            connection.exec_driver_sql(statement)
        assert write_state(connection) == "READ_ONLY"
        connection.execute(text(
            "INSERT INTO accounts (owner_id,name,account_type,classification,"
            "opening_balance_cents,active,created_at,updated_at) VALUES "
            "('second-replay','Synthetic preserved account','Checking','Personal',"
            "54321,true,now(),now())"
        ))
        connection.execute(text(
            "INSERT INTO goals (owner_id,name,goal_type,category,progress_source,"
            "current_progress_amount_cents,active,created_at,updated_at) VALUES "
            "('second-replay','Synthetic preserved goal','SAVINGS','FINANCIAL',"
            "'MANUAL',0,false,now(),now())"
        ))
        before = {
            table: connection.execute(text(
                f"SELECT row_to_json(r)::text FROM {table} r ORDER BY id"
            )).scalars().all()
            for table in ("accounts", "goals")
        }
        for number, statement in enumerate(second["statementsToExecute"], 1):
            try:
                connection.exec_driver_sql(statement)
            except Exception as error:
                raise AssertionError(f"Second Publish statement {number} failed") from error
        assert write_state(connection) == "NORMAL"
        for table, rows in before.items():
            assert connection.execute(text(
                f"SELECT row_to_json(r)::text FROM {table} r ORDER BY id"
            )).scalars().all() == rows
        assert "ck_goals_manual_progress_only" in {
            check["name"] for check in inspect(connection).get_check_constraints("goals")
        }
        # Every restored FK must use a true prerequisite constraint, not the
        # removed redundant standalone indexes. Inspect actual PostgreSQL binding.
        assert connection.scalar(text(
            "SELECT count(*) FROM pg_constraint fk "
            "JOIN pg_constraint parent ON parent.conindid=fk.conindid "
            "AND parent.contype='u' WHERE fk.contype='f' AND fk.conname IN "
            "('fk_opening_positions_owner_account','fk_opening_positions_owner_source',"
            "'fk_opening_positions_owner_instrument',"
            "'fk_opening_positions_owner_specification',"
            "'fk_investment_accounts_owner_account',"
            "'fk_cash_reconciliation_entries_owner_account',"
            "'fk_valuation_eligibility_owner_source')"
        )) == 7