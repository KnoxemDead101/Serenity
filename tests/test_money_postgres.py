"""Real PostgreSQL boundary coverage, using only a disposable private cluster."""

import os
import shutil
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

from auth import require_page_session, require_session
from main import app
from storage.database import get_db

OWNER = "postgres-money-test"
SMALL = 12345
OVER_INT32 = 2_147_483_648
SCHEMA_MAX = 100_000_000_000_000  # $1 trillion, in cents
TABLES = (
    "accounts", "bills", "debts", "investments", "transactions", "income_profiles",
)


def _alembic(url, *args, succeeds=True):
    # The only database connection this child receives is the disposable
    # Unix-socket URL. Never use the caller's DATABASE_URL.
    env = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run(
        ["alembic", *args], env=env, capture_output=True, text=True, timeout=90,
    )
    if succeeds:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0, "Unsafe downgrade unexpectedly succeeded"
    return result


@pytest.fixture(scope="module")
def postgres_url(tmp_path_factory):
    binaries = {name: shutil.which(name) for name in ("initdb", "postgres")}
    if not all(binaries.values()):
        if os.getenv("SERENITY_REQUIRE_POSTGRES") == "1":
            pytest.fail("PostgreSQL binaries required for money migration tests")
        pytest.skip("initdb/postgres not installed")
    root = tmp_path_factory.mktemp("isolated-money-pg")
    socket = root / "socket"
    socket.mkdir(mode=0o700)
    data = root / "cluster"
    subprocess.run(
        [binaries["initdb"], "-D", str(data), "-U", "moneytest",
         "--auth-local=trust", "--no-instructions"],
        check=True, capture_output=True, text=True, timeout=45,
    )
    # No TCP listener or external credentials; socket dir is unique and
    # private to this test process. PostgreSQL's own lock file guards its port.
    log = (root / "postgres.log").open("w")
    process = subprocess.Popen(
        [binaries["postgres"], "-D", str(data), "-h", "", "-k", str(socket),
         "-p", "55433"], stdout=log, stderr=subprocess.STDOUT,
    )
    url = f"postgresql://moneytest@/postgres?host={quote(str(socket))}&port=55433"
    try:
        from sqlalchemy import create_engine as connect_engine
        engine = connect_engine(url.replace("postgresql://", "postgresql+psycopg://", 1))
        deadline = time.monotonic() + 25
        while True:
            try:
                with engine.connect() as connection:
                    connection.execute(text("SELECT 1"))
                break
            except Exception:
                if process.poll() is not None or time.monotonic() > deadline:
                    pytest.fail("Disposable PostgreSQL failed to start")
                time.sleep(0.2)
        engine.dispose()
        yield url
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)
        log.close()


@pytest.fixture
def pg_engine(postgres_url):
    engine = create_engine(
        postgres_url.replace("postgresql://", "postgresql+psycopg://", 1),
    )
    try:
        yield engine
    finally:
        engine.dispose()


@pytest.fixture
def pg_client(pg_engine):
    factory = sessionmaker(bind=pg_engine, autoflush=False)

    def database():
        with factory() as db:
            yield db

    app.dependency_overrides[get_db] = database
    app.dependency_overrides[require_session] = lambda: OWNER
    app.dependency_overrides[require_page_session] = lambda: OWNER
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def _create(client, path, payload):
    result = client.post("/serenity-api/" + path, json=payload)
    assert result.status_code == 201, (path, result.text)
    return result.json()


def _seed_every_money_table(client, engine):
    account = _create(client, "accounts", {
        "name": "Savings", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "-123.45",
    })
    _create(client, f"accounts/{account['id']}/transactions", {
        "date": "2026-09-24", "transaction_type": "Income",
        "amount": "123.45", "description": "Test deposit",
    })
    _create(client, "bills", {
        "name": "Rent", "amount": "123.45", "due_date": "2026-10-01",
    })
    _create(client, "debts", {
        "name": "Card", "balance": "123.45", "minimum_payment": "123.45",
    })
    # This fixture deliberately runs at revision 0012. The current ORM
    # includes later columns, so seed the historical schema directly.
    with engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO investments (owner_id, name, quantity_units, "
            "cost_basis_cents, current_value_cents, active, created_at, updated_at) "
            "VALUES (:owner, 'Fund', 0, 12345, 12345, true, now(), now())"
        ), {"owner": OWNER})
    _create(client, "income-profiles", {
        "name": "Contract", "income_type": "Variable",
        "amount_per_period": "123.45",
    })
    return account


def _column_details(engine):
    with engine.connect() as connection:
        result = connection.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            "AND column_name LIKE '%_cents'"
        ))
        return {(row.table_name, row.column_name):
                (row.data_type, row.is_nullable, row.column_default) for row in result}


def test_postgres_money_migration_boundaries_and_downgrade(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "0012_investment_quantity_bigint")
    account = _seed_every_money_table(pg_client, pg_engine)
    before = _column_details(pg_engine)
    assert set(table for table, _ in before) == set(TABLES)
    assert all(typ == "integer" for typ, _, _ in before.values())
    before_indexes = {table: inspect(pg_engine).get_indexes(table) for table in TABLES}
    with pg_engine.begin() as connection:
        for (table, column) in before:
            connection.execute(text(f"UPDATE {table} SET {column} = :value"),
                               {"value": SMALL})
        connection.execute(text("UPDATE accounts SET opening_balance_cents = -12345"))
    _alembic(postgres_url, "upgrade", "0013_money_bigint")
    after = _column_details(pg_engine)
    assert set(after) == set(before), (before, after)
    assert all(typ == "bigint" and after[key][1:] == original[1:]
               for key, original in before.items() for typ in [after[key][0]])
    assert {table: inspect(pg_engine).get_indexes(table) for table in TABLES} == before_indexes
    with pg_engine.connect() as connection:
        for table, column in before:
            value = connection.scalar(text(f"SELECT {column} FROM {table} LIMIT 1"))
            assert value == (-SMALL if (table, column) ==
                             ("accounts", "opening_balance_cents") else SMALL)
    # A failed downgrade must leave the schema and data unchanged, including
    # other columns which would otherwise have already been altered.
    with pg_engine.begin() as connection:
        connection.execute(text(
            "UPDATE investments SET current_value_cents = :value"
        ), {"value": OVER_INT32})
    _alembic(postgres_url, "downgrade", "0012_investment_quantity_bigint", succeeds=False)
    assert _column_details(pg_engine) == after
    with pg_engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT current_value_cents FROM investments LIMIT 1"
        )) == OVER_INT32
    with pg_engine.begin() as connection:
        connection.execute(text("UPDATE investments SET current_value_cents = :value"),
                           {"value": SMALL})
    _alembic(postgres_url, "downgrade", "0012_investment_quantity_bigint")
    assert _column_details(pg_engine) == before
    _alembic(postgres_url, "upgrade", "0013_money_bigint")
    assert _column_details(pg_engine) == after
    assert account["id"] > 0


def test_postgres_api_boundary_money_dashboard_and_export(postgres_url, pg_engine, pg_client):
    # Also work when this test alone is selected with -k.
    _alembic(postgres_url, "upgrade", "head")
    with pg_engine.connect() as connection:
        from alembic.config import Config
        from alembic.script import ScriptDirectory
        heads = ScriptDirectory.from_config(Config("alembic.ini")).get_heads()
        assert set(connection.execute(text("SELECT version_num FROM alembic_version")).scalars()) == set(heads)
    account = _create(pg_client, "accounts", {
        "name": "Large negative balance", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "-1000000000000.00",
    })
    assert account["opening_balance"] == "-1000000000000.00"
    tx = _create(pg_client, f"accounts/{account['id']}/transactions", {
        "date": "2026-09-24", "transaction_type": "Income",
        "amount": "21474836.48", "description": "Over 32-bit cents",
    })
    assert tx["amount"] == "21474836.48"
    bill = _create(pg_client, "bills", {
        "name": "Maximum", "amount": "1000000000000.00",
        "due_date": "2026-10-01",
    })
    assert bill["amount"] == "1000000000000.00"
    debt = _create(pg_client, "debts", {
        "name": "Large debt", "balance": "21474836.48",
        "minimum_payment": "21474836.48",
    })
    assert debt["balance"] == "21474836.48"
    investment = _create(pg_client, "investments", {
        "name": "Long term", "cost_basis": "1000000000000.00",
        "current_value": "1000000000000.00",
    })
    assert investment["current_value"] == "1000000000000.00"
    profile = _create(pg_client, "income-profiles", {
        "name": "Large contract", "income_type": "Variable",
        "amount_per_period": "20000000.00",
    })
    assert profile["amount_per_period"] == "20000000.00"
    revised = pg_client.put(
        f"/serenity-api/accounts/{account['id']}/transactions/{tx['id']}",
        json={"date": "2026-09-25", "transaction_type": "Income",
              "amount": "1000000000000.00", "description": "Corrected deposit"},
    )
    assert revised.status_code == 200, revised.text
    assert revised.json()["amount"] == "1000000000000.00"
    corrections = pg_client.get(
        f"/serenity-api/accounts/{account['id']}/transaction-corrections"
    )
    assert corrections.status_code == 200
    assert corrections.json()
    summary = pg_client.get("/serenity-api/dashboard/summary")
    assert summary.status_code == 200, summary.text
    export = pg_client.get("/serenity-api/export")
    assert export.status_code == 200, export.text
    records = export.json()
    assert any(row["opening_balance_cents"] == -SCHEMA_MAX for row in records["accounts"])
    assert any(row["amount_cents"] == SCHEMA_MAX for row in records["transactions"])
    assert any(row["amount_per_period_cents"] == 2_000_000_000
               for row in records["income_profiles"])
    with pg_engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT opening_balance_cents FROM accounts WHERE id=:id"
        ), {"id": account["id"]}) == -SCHEMA_MAX