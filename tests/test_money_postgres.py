"""Real PostgreSQL boundary coverage, using only a disposable private cluster."""

import os
import shutil
import subprocess
import threading
import time
import hashlib
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker

from auth import require_page_session, require_session
from main import app
from models.account import Account
from schemas.transaction import TransactionCreate
from services import account_service, transaction_service
from services.financial_write_lock import lock_owner_financial_writes
from services.transaction_service import TransactionRuleError
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
        if args == ("upgrade", "head"):
            # Normal behavior regressions use the fully protected schema.
            # Explicit 0022 tests exercise staging without this restoration.
            # This URL comes exclusively from our private disposable cluster.
            from alembic.migration import MigrationContext
            from alembic.operations import Operations
            from migrations.publish_key_references import restore_references
            test_engine = create_engine(
                url.replace("postgresql://", "postgresql+psycopg://", 1),
            )
            try:
                with test_engine.begin() as connection:
                    restore_references(Operations(MigrationContext.configure(connection)))
            finally:
                test_engine.dispose()
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
    # This helper measures the legacy tables governed by revision 0013.
    # Later additive ledgers can also contain *_cents fields and are outside
    # that historical migration's boundary.
    table_filter = ", ".join(f"'{table}'" for table in TABLES)
    with engine.connect() as connection:
        result = connection.execute(text(
            "SELECT table_name, column_name, data_type, is_nullable, column_default "
            "FROM information_schema.columns WHERE table_schema = 'public' "
            f"AND column_name LIKE '%_cents' AND table_name IN ({table_filter})"
        ))
        return {(row.table_name, row.column_name):
                (row.data_type, row.is_nullable, row.column_default) for row in result}


def test_postgres_money_migration_boundaries_and_downgrade(
    postgres_url, pg_engine, pg_client,
):
    # Current account readers select the additive conversion ledger. Seed via
    # the current schema, then return to the historical revision before testing
    # the 0013 integer-width boundary itself.
    _alembic(postgres_url, "upgrade", "head")
    account = _seed_every_money_table(pg_client, pg_engine)
    _alembic(postgres_url, "downgrade", "0012_investment_quantity_bigint")
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

def test_postgres_approved_conversion_migration_is_additive_and_owner_scoped(
    postgres_url, pg_engine,
):
    """0016 preserves old balances and rejects cross-owner synthetic links."""
    _alembic(postgres_url, "upgrade", "0015_portfolio_containers")
    suffix = str(time.time_ns())
    owners = (f"conversion-a-{suffix}", f"conversion-b-{suffix}")
    records = {}
    with pg_engine.begin() as connection:
        for offset, owner in enumerate(owners):
            account_id = connection.scalar(text(
                "INSERT INTO accounts (owner_id, name, account_type, classification, "
                "opening_balance_cents, active, created_at, updated_at) "
                "VALUES (:owner, 'Synthetic cash', 'Brokerage', 'Personal', :balance, "
                "true, now(), now()) RETURNING id"
            ), {"owner": owner, "balance": 23456 + offset})
            portfolio_id = connection.scalar(text(
                "INSERT INTO portfolios (owner_id, name, active, created_at, updated_at) "
                "VALUES (:owner, 'Synthetic portfolio', true, now(), now()) RETURNING id"
            ), {"owner": owner})
            container_id = connection.scalar(text(
                "INSERT INTO investment_accounts (owner_id, portfolio_id, account_id, "
                "name, active, created_at, updated_at) "
                "VALUES (:owner, :portfolio, :account, 'Synthetic sleeve', true, now(), now()) "
                "RETURNING id"
            ), {"owner": owner, "portfolio": portfolio_id, "account": account_id})
            instrument_id = connection.scalar(text(
                "INSERT INTO instruments (owner_id, symbol, active, created_at, updated_at) "
                "VALUES (:owner, 'SYN', true, now(), now()) RETURNING id"
            ), {"owner": owner})
            specification_id = connection.scalar(text(
                "INSERT INTO instrument_specifications "
                "(instrument_id, owner_id, version, symbol, name, asset_type, currency, "
                "tick_size_units, point_value_units, created_at) "
                "VALUES (:instrument, :owner, 1, 'SYN', 'Synthetic security', 'equity', "
                "'USD', 1, 1, now()) RETURNING id"
            ), {"instrument": instrument_id, "owner": owner})
            investment_id = connection.scalar(text(
                "INSERT INTO investments (owner_id, name, ticker, quantity_units, "
                "cost_basis_cents, current_value_cents, active, created_at, updated_at) "
                "VALUES (:owner, 'Synthetic legacy holding', 'SYN', 100, 10000, 15000, "
                "true, now(), now()) RETURNING id"
            ), {"owner": owner})
            records[owner] = {
                "account": account_id,
                "portfolio": portfolio_id,
                "container": container_id,
                "instrument": instrument_id,
                "specification": specification_id,
                "investment": investment_id,
                "balance": 23456 + offset,
            }

    _alembic(postgres_url, "upgrade", "head")
    with pg_engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT version_num FROM alembic_version"
        )) == "0024_restore_publish_keys"
        for owner, facts in records.items():
            assert connection.scalar(text(
                "SELECT opening_balance_cents FROM accounts WHERE id = :id"
            ), {"id": facts["account"]}) == facts["balance"]
            assert connection.scalar(text(
                "SELECT current_value_cents FROM investments WHERE id = :id"
            ), {"id": facts["investment"]}) == 15000
        for table in (
            "reconciliation_approvals", "opening_positions",
            "valuation_eligibility", "cash_reconciliation_entries", "conversion_events",
        ):
            assert connection.scalar(text(f"SELECT count(*) FROM {table}")) == 0

    owner_a, owner_b = owners
    a, b = records[owner_a], records[owner_b]
    with pg_engine.begin() as connection:
        approval_id = connection.scalar(text(
            "INSERT INTO reconciliation_approvals "
            "(owner_id, canonical_report, report_format_version, algorithm_version, "
            "report_sha256, signed_token_evidence, preview_cutoff, source_fingerprint, "
            "approving_actor_id, approved_at, approved_source_ids, "
            "account_corrections_cents, before_component_totals_cents, "
            "after_component_totals_cents, expected_delta_cents, "
            "backup_evidence_reference, backup_cutoff, rollback_deadline, state) "
            "VALUES (:owner, decode('7b7d', 'hex'), 2, 'synthetic-v1', :digest, 'test-token', "
             "now(), 'synthetic-fingerprint', :actor, now(), '[]', '{}', '{}', '{}', 0, "
            "'synthetic-backup', now(), now(), 'approved') RETURNING id"
        ), {
            "owner": owner_a,
            "digest": "a" * 64,
            "actor": owner_a,
        })

    # Both child owner keys intentionally match owner A while the referenced
    # account/source belongs to owner B. Composite FKs must reject each row.
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO cash_reconciliation_entries "
                "(owner_id, approval_id, account_id, delta_cents, reason, evidence, "
                "before_balance_cents, after_balance_cents, actor_id, created_at) "
                "VALUES (:owner, :approval, :account, -1, 'combined_balance_overlap', "
                "'synthetic', 23456, 23455, :actor, now())"
            ), {
                "owner": owner_a, "approval": approval_id,
                "account": b["account"], "actor": owner_a,
            })
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(text(
                "INSERT INTO opening_positions "
                "(owner_id, approval_id, source_investment_id, portfolio_id, "
                "investment_account_id, cash_account_id, instrument_id, specification_id, "
                "specification_version, quantity_units, entered_basis_cents, basis_status, "
                "original_entered_value_cents, captured_at, source_snapshot, status) "
                "VALUES (:owner, :approval, :source, :portfolio, :container, :account, "
                ":instrument, :specification, 1, 100, 10000, 'known', 15000, now(), '{}', 'active')"
            ), {
                "owner": owner_a, "approval": approval_id,
                "source": b["investment"], "portfolio": a["portfolio"],
                "container": a["container"], "account": a["account"],
                "instrument": a["instrument"], "specification": a["specification"],
            })

    _alembic(postgres_url, "downgrade", "0015_portfolio_containers", succeeds=False)
    with pg_engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT version_num FROM alembic_version"
        )) == "0024_restore_publish_keys"
        assert connection.scalar(text(
            "SELECT opening_balance_cents FROM accounts WHERE id = :id"
        ), {"id": a["account"]}) == a["balance"]
        assert connection.scalar(text(
            "SELECT opening_balance_cents FROM accounts WHERE id = :id"
        ), {"id": b["account"]}) == b["balance"]
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

def test_postgres_owner_lock_isolation_and_stale_account_refresh(postgres_url, pg_engine):
    """Different owners proceed independently; writers refresh stale ORM rows."""
    from datetime import date

    from sqlalchemy import select
    from sqlalchemy.orm import sessionmaker

    from schemas.account import AccountCreate

    _alembic(postgres_url, "upgrade", "head")
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)
    owner_a, owner_b = f"synthetic-lock-a-{time.time_ns()}", f"synthetic-lock-b-{time.time_ns()}"
    second_owner_acquired = threading.Event()
    errors = []

    first = factory()
    try:
        lock_owner_financial_writes(first, owner_a)

        def acquire_other_owner():
            try:
                with factory.begin() as other:
                    lock_owner_financial_writes(other, owner_b)
                second_owner_acquired.set()
            except BaseException as exc:
                errors.append(exc)

        worker = threading.Thread(target=acquire_other_owner)
        worker.start()
        assert second_owner_acquired.wait(5), "An owner's lock blocked an unrelated owner"
        worker.join(5)
        assert not worker.is_alive()
        assert not errors
    finally:
        first.rollback()
        first.close()

    with factory() as seed:
        account = account_service.create_account(
            seed,
            AccountCreate(
                name="Synthetic stale-row account", account_type="Checking",
                classification="Personal", opening_balance="0",
            ),
            owner_a,
        )
        account_id = account.id

    stale_session = factory()
    try:
        stale = stale_session.scalar(select(Account).where(
            Account.id == account_id, Account.owner_id == owner_a,
        ))
        assert stale is not None and stale.active
        with factory() as writer:
            current = writer.scalar(select(Account).where(Account.id == account_id))
            account_service.set_account_active(writer, current, False)

        with pytest.raises(TransactionRuleError, match="deactivated"):
            transaction_service.create_transaction(
                stale_session,
                stale,
                TransactionCreate(
                    date=date(2026, 1, 2), transaction_type="Income",
                    amount="1.00", description="Synthetic stale-session check",
                ),
            )
    finally:
        stale_session.rollback()
        stale_session.close()

def test_postgres_conversion_and_shared_financial_lock_protocol(
    postgres_url, pg_engine,
):
    """Conversion locks serialize with ordinary writers but not another owner."""
    from sqlalchemy.orm import sessionmaker

    from services.conversion_service import _lock_owner

    _alembic(postgres_url, "upgrade", "head")
    factory = sessionmaker(bind=pg_engine)
    owner_a = f"conversion-lock-a-{time.time_ns()}"
    owner_b = f"conversion-lock-b-{time.time_ns()}"
    first = factory()
    same_owner_acquired = threading.Event()
    other_owner_acquired = threading.Event()
    errors = []

    try:
        _lock_owner(first, owner_a)

        def acquire(owner_id, acquired):
            try:
                with factory.begin() as writer:
                    lock_owner_financial_writes(writer, owner_id)
                acquired.set()
            except BaseException as exc:
                errors.append(exc)

        same_owner = threading.Thread(
            target=acquire, args=(owner_a, same_owner_acquired),
        )
        different_owner = threading.Thread(
            target=acquire, args=(owner_b, other_owner_acquired),
        )
        same_owner.start()
        different_owner.start()
        assert other_owner_acquired.wait(5), "Other owner was blocked by conversion lock"
        assert not same_owner_acquired.wait(0.2), "Shared writer bypassed conversion lock"
        first.commit()
        same_owner.join(5)
        different_owner.join(5)
        assert same_owner_acquired.is_set()
        assert not same_owner.is_alive() and not different_owner.is_alive()
        assert not errors
    finally:
        first.rollback()
        first.close()

def test_postgres_two_owner_conversion_execution_proof(
    postgres_url, pg_engine, pg_client, monkeypatch,
):
    """Exercise approvals, ledgers, totals, owner isolation and lock contention."""
    from sqlalchemy import delete, select
    from sqlalchemy.orm import sessionmaker

    from auth import require_session
    from models.account import Account
    from models.conversion import (
        CashReconciliationEntry, ConversionEvent, OpeningPosition,
        ReconciliationApproval, ValuationEligibility,
    )
    from models.investment import Investment
    from schemas.account import AccountCreate
    from schemas.conversion import ExecuteRequest
    from services import account_service, conversion_service

    _alembic(postgres_url, "upgrade", "head")
    monkeypatch.setenv("SERENITY_CONVERSION_TEST_MODE", "1")
    monkeypatch.setenv("SERENITY_CONVERSION_POSTGRES_TEST_MODE", "1")
    monkeypatch.setenv("SERENITY_CONVERSION_POSTGRES_TEST_DATABASE_URL", postgres_url)
    owner_suffix = time.time_ns() % 10**10
    owner_a = f"cpa{owner_suffix}"
    owner_b = f"cpb{owner_suffix}"
    active_owner = {"id": owner_a}
    monkeypatch.setitem(app.dependency_overrides, require_session, lambda: active_owner["id"])
    factory = sessionmaker(bind=pg_engine, autoflush=False, expire_on_commit=False)

    def setup_owner(owner_id, symbol):
        active_owner["id"] = owner_id
        account = _create(pg_client, "accounts", {
            "name": f"{symbol} brokerage", "account_type": "Brokerage",
            "classification": "Personal", "opening_balance": "10000",
        })
        portfolio = _create(pg_client, "portfolios", {"name": f"{symbol} portfolio"})
        container = _create(pg_client, "investment-accounts", {
            "name": f"{symbol} sleeve", "portfolio_id": portfolio["id"],
            "account_id": account["id"],
        })
        instrument = _create(pg_client, "instruments", {
            "symbol": symbol, "name": symbol, "asset_type": "STOCK",
        })
        source = _create(pg_client, "investments", {
            "name": f"{symbol} shares", "ticker": symbol, "quantity": "40",
            "cost_basis": "6000", "current_value": "8000",
        })
        preview = pg_client.post("/serenity-api/reconciliation/execution-preview", json={
            "mappings": [{
                "source_id": source["id"], "investment_account_id": container["id"],
                "instrument_id": instrument["id"], "specification_id": instrument["specification_id"],
                "identity_confirmed": True, "beneficial_ownership": "personal",
                "basis_status": "unverified",
            }],
            "accounts": [{
                "account_id": account["id"], "balance_meaning": "combined",
                "cash_cents": 200000, "evidence": "Disposable PostgreSQL test statement",
                "complete": True, "source_ids": [source["id"]],
            }],
        })
        assert preview.status_code == 200, preview.text
        return account, source, preview.json()

    def approval_body(account, source, preview):
        report = preview["report"]
        digest = hashlib.sha256(
            json.dumps(report, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")
        ).hexdigest()
        account_row = next(row for row in report["accounts"] if row["account"]["id"] == account["id"])
        now = datetime.now(timezone.utc)
        return {
            "report_token": preview["report_token"], "report_sha256": digest,
            "selected_source_ids": [source["id"]],
            "account_corrections_cents": {
                str(account["id"]): account_row["correction_cents"],
            },
            "backup_evidence_reference": "synthetic://disposable-postgres-test",
            "backup_cutoff": (now - timedelta(minutes=1)).isoformat(),
            "rollback_deadline": (now + timedelta(days=1)).isoformat(),
            "confirm_approval": True, "test_only_synthetic": True,
        }

    def create_and_remove_probe(owner_id):
        with factory() as db:
            probe = account_service.create_account(db, AccountCreate(
                name="Disposable lock probe", account_type="Checking",
                classification="Personal", opening_balance="0",
            ), owner_id)
            db.execute(delete(Account).where(
                Account.owner_id == owner_id, Account.id == probe.id,
            ))
            db.commit()

    account_a, source_a, preview_a = setup_owner(owner_a, "PGCONVA")
    report_a = preview_a["report"]
    assert report_a["current"]["net_worth_cents"] == 1800000
    approval_a_response = pg_client.post(
        "/serenity-api/conversions/approvals",
        json=approval_body(account_a, source_a, preview_a),
    )
    assert approval_a_response.status_code == 201, approval_a_response.text
    approval_a = approval_a_response.json()["approval_id"]

    entered = threading.Event()
    release = threading.Event()
    same_owner_done = threading.Event()
    other_owner_done = threading.Event()
    thread_errors = []
    execution_result = {}

    def hold_after_ledger_writes():
        entered.set()
        if not release.wait(10):
            raise TimeoutError("test did not release the synthetic conversion transaction")

    monkeypatch.setattr(
        conversion_service, "_after_conversion_ledger_writes", hold_after_ledger_writes,
    )

    def execute_owner_a():
        try:
            with factory() as db:
                execution_result["result"] = conversion_service.execute(
                    db, owner_a, owner_a, approval_a,
                    ExecuteRequest(
                        idempotency_key="postgres-conversion-a",
                        confirm_execute=True,
                    ),
                )
        except BaseException as exc:
            thread_errors.append(exc)

    def compete(owner_id, done):
        try:
            create_and_remove_probe(owner_id)
            done.set()
        except BaseException as exc:
            thread_errors.append(exc)

    execution_thread = threading.Thread(target=execute_owner_a)
    execution_thread.start()
    try:
        assert entered.wait(10), (
            "Conversion execution did not reach its held ledger transaction: "
            f"{execution_result.get('result')}, errors={thread_errors}"
        )
        same_owner_thread = threading.Thread(target=compete, args=(owner_a, same_owner_done))
        other_owner_thread = threading.Thread(target=compete, args=(owner_b, other_owner_done))
        same_owner_thread.start()
        other_owner_thread.start()
        assert other_owner_done.wait(5), "Unrelated owner writer was serialized behind conversion"
        assert not same_owner_done.wait(0.2), "Same-owner writer bypassed conversion's lock"
    finally:
        release.set()
        execution_thread.join(10)
        if "same_owner_thread" in locals():
            same_owner_thread.join(10)
        if "other_owner_thread" in locals():
            other_owner_thread.join(10)
    assert not execution_thread.is_alive()
    assert not thread_errors, thread_errors
    response_a = execution_result["result"]
    assert same_owner_done.is_set() and other_owner_done.is_set()
    assert response_a["before_totals"] == report_a["current"]
    assert response_a["after_totals"] == report_a["proposed"]
    assert response_a["after_totals"]["account_balance_cents"] == 200000
    assert response_a["after_totals"]["holding_value_cents"] == 800000

    # Repeated concurrent requests with the same approval/key converge on
    # the one committed event and return its exact result.
    retry_barrier = threading.Barrier(4)
    retry_results = []
    retry_errors = []

    def retry_execution():
        try:
            with factory() as db:
                retry_barrier.wait(10)
                retry_results.append(conversion_service.execute(
                    db, owner_a, owner_a, approval_a,
                    ExecuteRequest(
                        idempotency_key="postgres-conversion-a",
                        confirm_execute=True,
                    ),
                ))
        except BaseException as exc:
            retry_errors.append(exc)

    retry_threads = [threading.Thread(target=retry_execution) for _ in range(3)]
    for worker in retry_threads:
        worker.start()
    retry_barrier.wait(10)
    for worker in retry_threads:
        worker.join(10)
    assert all(not worker.is_alive() for worker in retry_threads)
    assert not retry_errors, retry_errors
    assert len(retry_results) == 3
    assert all(result == response_a for result in retry_results)
    with factory() as db:
        assert db.query(ConversionEvent).filter_by(
            owner_id=owner_a, approval_id=approval_a, event_kind="executed",
        ).count() == 1

    # Two distinct approved reports overlap the same source. Only one can
    # commit, and the rejected execution must leave no partial ledger rows.
    owner_c = f"cpc{owner_suffix}"
    account_c, source_c, preview_c1 = setup_owner(owner_c, "PGCONVC")
    approval_c1_response = pg_client.post(
        "/serenity-api/conversions/approvals",
        json=approval_body(account_c, source_c, preview_c1),
    )
    assert approval_c1_response.status_code == 201, approval_c1_response.text
    approval_c1 = approval_c1_response.json()["approval_id"]
    mapping_c = preview_c1["report"]["sources"][0]["mapping"]
    preview_c2_response = pg_client.post(
        "/serenity-api/reconciliation/execution-preview", json={
            "mappings": [{
                "source_id": source_c["id"],
                "investment_account_id": mapping_c["investment_account_id"],
                "instrument_id": mapping_c["instrument_id"],
                "specification_id": mapping_c["specification_id"],
                "identity_confirmed": True, "beneficial_ownership": "personal",
                "basis_status": "unverified",
            }],
            "accounts": [{
                "account_id": account_c["id"], "balance_meaning": "combined",
                "cash_cents": 200000, "evidence": "Second independently reviewed statement",
                "complete": True, "source_ids": [source_c["id"]],
            }],
        },
    )
    assert preview_c2_response.status_code == 200, preview_c2_response.text
    preview_c2 = preview_c2_response.json()
    approval_c2_response = pg_client.post(
        "/serenity-api/conversions/approvals",
        json=approval_body(account_c, source_c, preview_c2),
    )
    assert approval_c2_response.status_code == 201, approval_c2_response.text
    approval_c2 = approval_c2_response.json()["approval_id"]
    assert approval_c1 != approval_c2

    overlap_barrier = threading.Barrier(3)
    overlap_results = []
    overlap_errors = []

    def execute_overlap(approval_id, idempotency_key):
        try:
            with factory() as db:
                overlap_barrier.wait(10)
                overlap_results.append(conversion_service.execute(
                    db, owner_c, owner_c, approval_id,
                    ExecuteRequest(idempotency_key=idempotency_key, confirm_execute=True),
                ))
        except BaseException as exc:
            overlap_errors.append(exc)

    overlap_threads = [
        threading.Thread(target=execute_overlap, args=(approval_c1, "overlap-c1")),
        threading.Thread(target=execute_overlap, args=(approval_c2, "overlap-c2")),
    ]
    for worker in overlap_threads:
        worker.start()
    overlap_barrier.wait(10)
    for worker in overlap_threads:
        worker.join(10)
    assert all(not worker.is_alive() for worker in overlap_threads)
    assert len(overlap_results) == 1, (overlap_results, overlap_errors)
    assert len(overlap_errors) == 1
    assert isinstance(overlap_errors[0], conversion_service.ConversionConflict)
    with factory() as db:
        assert overlap_results[0]["approval_id"] in (approval_c1, approval_c2)
        assert db.query(ReconciliationApproval).filter_by(
            owner_id=owner_c, state="executed",
        ).count() == 1
        assert db.query(ReconciliationApproval).filter_by(
            owner_id=owner_c, state="approved",
        ).count() == 1
        assert db.query(OpeningPosition).filter_by(owner_id=owner_c).count() == 1
        assert db.query(ValuationEligibility).filter_by(owner_id=owner_c).count() == 1
        assert db.query(CashReconciliationEntry).filter_by(owner_id=owner_c).count() == 1
        assert db.query(ConversionEvent).filter_by(
            owner_id=owner_c, event_kind="executed",
        ).count() == 1

    # Keep source and approval ORM objects preloaded, edit the source, then
    # execute a newly previewed/approved report through that stale session.
    owner_d = f"cpd{owner_suffix}"
    account_d, source_d, preview_d_old = setup_owner(owner_d, "PGCONVD")
    old_approval_response = pg_client.post(
        "/serenity-api/conversions/approvals",
        json=approval_body(account_d, source_d, preview_d_old),
    )
    assert old_approval_response.status_code == 201, old_approval_response.text
    old_approval_id = old_approval_response.json()["approval_id"]
    stale_session = factory()
    try:
        stale_source = stale_session.scalar(select(Investment).where(
            Investment.owner_id == owner_d, Investment.id == source_d["id"],
        ))
        stale_approval = stale_session.scalar(select(ReconciliationApproval).where(
            ReconciliationApproval.owner_id == owner_d,
            ReconciliationApproval.id == old_approval_id,
        ))
        assert stale_source.quantity_units == 4_000_000_000
        assert stale_source.current_value_cents == 800000
        assert stale_approval.state == "approved"

        active_owner["id"] = owner_d
        edited = pg_client.put(f"/serenity-api/investments/{source_d['id']}", json={
            "name": "Freshly edited synthetic shares", "ticker": "PGCONVD",
            "quantity": "50", "cost_basis": "7000", "current_value": "9000",
        })
        assert edited.status_code == 200, edited.text
        mapping_d = preview_d_old["report"]["sources"][0]["mapping"]
        fresh_preview_response = pg_client.post(
            "/serenity-api/reconciliation/execution-preview", json={
                "mappings": [{
                    "source_id": source_d["id"],
                    "investment_account_id": mapping_d["investment_account_id"],
                    "instrument_id": mapping_d["instrument_id"],
                    "specification_id": mapping_d["specification_id"],
                    "identity_confirmed": True, "beneficial_ownership": "personal",
                    "basis_status": "unverified",
                }],
                "accounts": [{
                    "account_id": account_d["id"], "balance_meaning": "combined",
                    "cash_cents": 100000, "evidence": "Fresh edited source statement",
                    "complete": True, "source_ids": [source_d["id"]],
                }],
            },
        )
        assert fresh_preview_response.status_code == 200, fresh_preview_response.text
        fresh_preview = fresh_preview_response.json()
        fresh_source = fresh_preview["report"]["sources"][0]["source"]
        assert fresh_source["quantity_units"] == 5_000_000_000
        assert fresh_source["current_value_cents"] == 900000
        fresh_approval_response = pg_client.post(
            "/serenity-api/conversions/approvals",
            json=approval_body(account_d, source_d, fresh_preview),
        )
        assert fresh_approval_response.status_code == 201, fresh_approval_response.text
        fresh_approval_id = fresh_approval_response.json()["approval_id"]
        preloaded_fresh_approval = stale_session.scalar(select(ReconciliationApproval).where(
            ReconciliationApproval.owner_id == owner_d,
            ReconciliationApproval.id == fresh_approval_id,
        ))
        assert preloaded_fresh_approval.state == "approved"
        preloaded_report = json.loads(preloaded_fresh_approval.canonical_report)
        assert preloaded_report["sources"][0]["source"]["current_value_cents"] == 900000
        fresh_result = conversion_service.execute(
            stale_session, owner_d, owner_d, fresh_approval_id,
            ExecuteRequest(
                idempotency_key="postgres-fresh-edited-source",
                confirm_execute=True,
            ),
        )
        assert fresh_result["after_totals"] == fresh_preview["report"]["proposed"]
        opening = stale_session.scalar(select(OpeningPosition).where(
            OpeningPosition.owner_id == owner_d,
            OpeningPosition.source_investment_id == source_d["id"],
        ))
        assert opening.quantity_units == 5_000_000_000
        assert opening.entered_basis_cents == 700000
        assert opening.original_entered_value_cents == 900000
        source_snapshot = json.loads(opening.source_snapshot)
        assert source_snapshot["quantity_units"] == 5_000_000_000
        assert source_snapshot["current_value_cents"] == 900000
    finally:
        stale_session.rollback()
        stale_session.close()

    account_b, source_b, preview_b = setup_owner(owner_b, "PGCONVB")
    report_b = preview_b["report"]
    approval_b_response = pg_client.post(
        "/serenity-api/conversions/approvals",
        json=approval_body(account_b, source_b, preview_b),
    )
    assert approval_b_response.status_code == 201, approval_b_response.text
    approval_b = approval_b_response.json()["approval_id"]

    active_owner["id"] = owner_b
    assert pg_client.get(f"/serenity-api/conversions/{approval_a}").status_code == 404
    assert pg_client.get(
        f"/serenity-api/conversions/{approval_a}/evidence"
    ).status_code == 404
    cross_owner_approval = pg_client.post(
        "/serenity-api/conversions/approvals",
        json=approval_body(account_a, source_a, preview_a),
    )
    assert cross_owner_approval.status_code == 404
    assert pg_client.post(
        f"/serenity-api/conversions/{approval_a}/execute",
        json={"idempotency_key": "cross-owner-attempt", "confirm_execute": True},
    ).status_code == 404
    assert pg_client.post(
        f"/serenity-api/conversions/{approval_a}/reverse",
        json={"reason": "Cross-owner test", "confirm_reverse": True},
    ).status_code == 404

    active_owner["id"] = owner_a
    reversed_a = pg_client.post(
        f"/serenity-api/conversions/{approval_a}/reverse",
        json={"reason": "Reverse disposable owner A conversion", "confirm_reverse": True},
    )
    assert reversed_a.status_code == 200, reversed_a.text
    assert reversed_a.json()["after_totals"] == report_a["current"]

    active_owner["id"] = owner_b
    response_b = pg_client.post(
        f"/serenity-api/conversions/{approval_b}/execute",
        json={"idempotency_key": "postgres-conversion-b", "confirm_execute": True},
    )
    assert response_b.status_code == 200, response_b.text
    assert response_b.json()["before_totals"] == report_b["current"]
    assert response_b.json()["after_totals"] == report_b["proposed"]
    assert response_b.json()["after_totals"]["account_balance_cents"] == 200000
    assert response_b.json()["after_totals"]["holding_value_cents"] == 800000
    reversed_b = pg_client.post(
        f"/serenity-api/conversions/{approval_b}/reverse",
        json={"reason": "Reverse disposable owner B conversion", "confirm_reverse": True},
    )
    assert reversed_b.status_code == 200, reversed_b.text
    assert reversed_b.json()["after_totals"] == report_b["current"]
