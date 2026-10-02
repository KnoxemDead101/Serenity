"""All stored cents must fit the amounts accepted by the API."""

import importlib
import pkgutil
import sqlite3
import subprocess
import sys
import os
from decimal import Decimal

import pytest
from alembic.migration import MigrationContext
from alembic.operations import Operations
from pydantic import ValidationError
from sqlalchemy import BigInteger, Text, create_engine

import models
from schemas.account import AccountCreate
from schemas.finance import InvestmentCreate
from schemas.income_profile import IncomeProfileCreate
from storage.database import Base
from utils.validators import MAX_MONEY, validate_money

money_migration = importlib.import_module("migrations.versions.0013_money_bigint")
conversion_migration = importlib.import_module(
    "migrations.versions.0016_approved_conversions"
)
approval_delta_migration = importlib.import_module(
    "migrations.versions.0017_conversion_guards"
)

CONVERSION_TABLES = {
    "reconciliation_approvals",
    "opening_positions",
    "cash_reconciliation_entries",
}
CENT_TEXT_DOCUMENTS = {
    ("reconciliation_approvals", "account_corrections_cents"),
    ("reconciliation_approvals", "before_component_totals_cents"),
    ("reconciliation_approvals", "after_component_totals_cents"),
}


def test_every_mapped_cent_field_is_bigint_and_in_migration():
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"models.{module.name}")
    mapped = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith("_cents")
    }
    legacy_mapped = {
        (table, column)
        for table, columns in money_migration.MONEY_COLUMNS.items()
        for column in columns
    }
    conversion_mapped = {
        key for key in mapped if key[0] in CONVERSION_TABLES
    }
    # Goal Core and Composition add already-BIGINT fields in their own migrations.
    goal_columns = {
        ("goals", "target_amount_cents"),
        ("goals", "current_progress_amount_cents"),
    }
    composition_columns = {
        ("goal_items", "expected_cost_cents"),
        ("goal_items", "manual_actual_cost_override_cents"),
        ("goal_checkpoints", "amount_cents"),
    }
    assert len(legacy_mapped) == 11
    assert mapped - conversion_mapped == legacy_mapped | goal_columns | composition_columns
    assert conversion_migration.down_revision == "0015_portfolio_containers"
    assert conversion_migration.revision == "0016_approved_conversions"
    assert approval_delta_migration.down_revision == conversion_migration.revision
    assert approval_delta_migration.revision == "0017_conversion_guards"
    assert conversion_mapped - CENT_TEXT_DOCUMENTS == {
        ("opening_positions", "entered_basis_cents"),
        ("opening_positions", "original_entered_value_cents"),
        ("cash_reconciliation_entries", "delta_cents"),
        ("cash_reconciliation_entries", "before_balance_cents"),
        ("cash_reconciliation_entries", "after_balance_cents"),
        ("reconciliation_approvals", "expected_delta_cents"),
    }
    for table, column in mapped - CENT_TEXT_DOCUMENTS:
        assert isinstance(Base.metadata.tables[table].c[column].type, BigInteger)
    assert money_migration.down_revision == "0012_investment_quantity_bigint"


def test_all_validated_money_fits_signed_bigint():
    assert int(MAX_MONEY * 100) <= 2**63 - 1
    assert validate_money(MAX_MONEY, "Amount") == MAX_MONEY
    assert validate_money(-MAX_MONEY, "Amount") == -MAX_MONEY
    with pytest.raises(ValueError):
        validate_money(MAX_MONEY + Decimal("0.01"), "Amount")
    assert AccountCreate(
        name="Savings", account_type="Savings", classification="Personal",
        opening_balance=str(MAX_MONEY),
    ).opening_balance == MAX_MONEY
    assert AccountCreate(
        name="Savings", account_type="Savings", classification="Personal",
        opening_balance=f"-{MAX_MONEY}",
    ).opening_balance == -MAX_MONEY
    with pytest.raises(ValidationError):
        InvestmentCreate(name="Fund", cost_basis=str(MAX_MONEY + 1),
                         current_value="1")
    assert IncomeProfileCreate(
        name="Salary", income_type="Salary", annual_salary="20000000",
        pay_frequency="Monthly",
    ).annual_salary == Decimal("20000000")


@pytest.mark.parametrize("amount", [2**31, -(2**31) - 1])
def test_sqlite_downgrade_refuses_unsafe_money_without_changing_revision(
    tmp_path, amount,
):
    path = tmp_path / "isolated-money.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}"}
    upgrade = subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"],
                             env=env, capture_output=True, text=True)
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO accounts (name, account_type, classification, "
            "opening_balance_cents, owner_id, created_at, updated_at, active) "
            "VALUES ('test', 'Savings', 'Personal', ?, 'test-owner', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 1)", (amount,),
        )
    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade",
         "0012_investment_quantity_bigint"],
        env=env, capture_output=True, text=True,
    )
    assert downgrade.returncode != 0
    assert "Cannot narrow accounts.opening_balance_cents" in downgrade.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0013_money_bigint"
        )
        assert db.execute(
            "SELECT opening_balance_cents FROM accounts"
        ).fetchone()[0] == amount

def test_sqlite_approved_conversion_migration_is_additive_and_owner_scoped(tmp_path):
    path = tmp_path / "isolated-conversion.db"
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}"}
    upgrade_legacy = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0015_portfolio_containers"],
        env=env, capture_output=True, text=True,
    )
    assert upgrade_legacy.returncode == 0, upgrade_legacy.stderr

    owners = ("synthetic-conversion-a", "synthetic-conversion-b")
    records = {}
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        for offset, owner in enumerate(owners):
            account_id = 700 + offset
            portfolio_id = 800 + offset
            container_id = 900 + offset
            instrument_id = 1000 + offset
            specification_id = 1100 + offset
            investment_id = 1200 + offset
            balance = 23456 + offset
            db.execute(
                "INSERT INTO accounts (id, owner_id, name, account_type, classification, "
                "opening_balance_cents, active, created_at, updated_at) "
                "VALUES (?, ?, 'Synthetic cash', 'Brokerage', 'Personal', ?, 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (account_id, owner, balance),
            )
            db.execute(
                "INSERT INTO portfolios (id, owner_id, name, active, created_at, updated_at) "
                "VALUES (?, ?, 'Synthetic portfolio', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (portfolio_id, owner),
            )
            db.execute(
                "INSERT INTO investment_accounts (id, owner_id, portfolio_id, account_id, "
                "name, active, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, 'Synthetic sleeve', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (container_id, owner, portfolio_id, account_id),
            )
            db.execute(
                "INSERT INTO instruments (id, owner_id, symbol, active, created_at, updated_at) "
                "VALUES (?, ?, 'SYN', 1, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (instrument_id, owner),
            )
            db.execute(
                "INSERT INTO instrument_specifications "
                "(id, instrument_id, owner_id, version, symbol, name, asset_type, currency, "
                "tick_size_units, point_value_units, created_at) "
                "VALUES (?, ?, ?, 1, 'SYN', 'Synthetic security', 'equity', 'USD', 1, 1, "
                "CURRENT_TIMESTAMP)",
                (specification_id, instrument_id, owner),
            )
            db.execute(
                "INSERT INTO investments (id, owner_id, name, ticker, quantity_units, "
                "cost_basis_cents, current_value_cents, active, created_at, updated_at) "
                "VALUES (?, ?, 'Synthetic legacy holding', 'SYN', 100, 10000, 15000, 1, "
                "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)",
                (investment_id, owner),
            )
            records[owner] = {
                "account": account_id,
                "portfolio": portfolio_id,
                "container": container_id,
                "instrument": instrument_id,
                "specification": specification_id,
                "investment": investment_id,
                "balance": balance,
            }

    upgrade_conversion = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True,
    )
    assert upgrade_conversion.returncode == 0, upgrade_conversion.stderr
    with sqlite3.connect(path) as db:
        db.execute("PRAGMA foreign_keys = ON")
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0024_restore_publish_keys"
        )
        for owner, facts in records.items():
            assert db.execute(
                "SELECT opening_balance_cents FROM accounts WHERE id = ?",
                (facts["account"],),
            ).fetchone()[0] == facts["balance"]
            assert db.execute(
                "SELECT current_value_cents FROM investments WHERE id = ?",
                (facts["investment"],),
            ).fetchone()[0] == 15000
        conversion_tables = (
            "reconciliation_approvals", "opening_positions",
            "valuation_eligibility", "cash_reconciliation_entries", "conversion_events",
        )
        assert all(
            db.execute(f"SELECT count(*) FROM {table}").fetchone()[0] == 0
            for table in conversion_tables
        )
        owner_a, owner_b = owners
        a, b = records[owner_a], records[owner_b]
        db.execute(
            "INSERT INTO reconciliation_approvals "
            "(owner_id, canonical_report, report_format_version, algorithm_version, "
            "report_sha256, signed_token_evidence, preview_cutoff, source_fingerprint, "
            "approving_actor_id, approved_at, approved_source_ids, account_corrections_cents, "
            "before_component_totals_cents, after_component_totals_cents, expected_delta_cents, "
            "backup_evidence_reference, backup_cutoff, rollback_deadline, state) "
            "VALUES (?, ?, 2, 'synthetic-v1', ?, 'test-token', CURRENT_TIMESTAMP, "
             "'synthetic-fingerprint', ?, CURRENT_TIMESTAMP, '[]', '{}', '{}', '{}', -1234567890123, "
            "'synthetic-backup', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'approved')",
            (owner_a, b"{}", "a" * 64, owner_a),
        )
        approval_id = db.execute(
            "SELECT id FROM reconciliation_approvals WHERE owner_id = ?", (owner_a,)
        ).fetchone()[0]
        assert db.execute(
            "SELECT expected_delta_cents, typeof(expected_delta_cents) "
            "FROM reconciliation_approvals WHERE id = ?",
            (approval_id,),
        ).fetchone() == (-1234567890123, "integer")

        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO cash_reconciliation_entries "
                "(owner_id, approval_id, account_id, delta_cents, reason, evidence, "
                "before_balance_cents, after_balance_cents, actor_id, created_at) "
                "VALUES (?, ?, ?, -1, 'combined_balance_overlap', 'synthetic', "
                "23456, 23455, ?, CURRENT_TIMESTAMP)",
                (owner_a, approval_id, b["account"], owner_a),
            )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                "INSERT INTO opening_positions "
                "(owner_id, approval_id, source_investment_id, portfolio_id, "
                "investment_account_id, cash_account_id, instrument_id, specification_id, "
                "specification_version, quantity_units, entered_basis_cents, basis_status, "
                "original_entered_value_cents, captured_at, source_snapshot, status) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, 100, 10000, 'known', 15000, "
                "CURRENT_TIMESTAMP, '{}', 'active')",
                (
                    owner_a, approval_id, b["investment"], a["portfolio"],
                    a["container"], a["account"], a["instrument"], a["specification"],
                ),
            )

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0015_portfolio_containers"],
        env=env, capture_output=True, text=True,
    )
    assert downgrade.returncode != 0
    assert "Cannot downgrade" in downgrade.stderr
    with sqlite3.connect(path) as db:
        # SQLite can complete the no-op 0021 downgrade before the 0020
        # history guard refuses; all financial records remain protected.
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0020_conversion_integration"
        )
        assert db.execute(
            "SELECT opening_balance_cents FROM accounts WHERE id = ?",
            (records[owners[0]]["account"],),
        ).fetchone()[0] == records[owners[0]]["balance"]
        assert db.execute(
            "SELECT opening_balance_cents FROM accounts WHERE id = ?",
            (records[owners[1]]["account"],),
        ).fetchone()[0] == records[owners[1]]["balance"]

def _create_applied_0016_database(path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{path}"}
    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "0016_approved_conversions"],
        env=env, capture_output=True, text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    _simulate_early_text_0016(path)
    return env

def _simulate_early_text_0016(path):
    """Rebuild empty synthetic 0016 schema as if its delta column were TEXT."""
    engine = create_engine(f"sqlite:///{path}")
    with engine.begin() as connection:
        trigger_definitions = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' "
            "AND tbl_name = 'reconciliation_approvals'"
        ).scalars().all()
        operations = Operations(MigrationContext.configure(connection))
        with operations.batch_alter_table("reconciliation_approvals") as batch:
            batch.alter_column(
                "expected_delta_cents",
                existing_type=BigInteger(),
                type_=Text(),
                existing_nullable=False,
            )
        for definition in trigger_definitions:
            connection.exec_driver_sql(definition)
    engine.dispose()

def test_0017_converts_empty_early_text_0016_and_retains_approval_guards(tmp_path):
    path = tmp_path / "early-text-0016.db"
    env = _create_applied_0016_database(path)
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT type FROM pragma_table_info('reconciliation_approvals') "
            "WHERE name = 'expected_delta_cents'"
        ).fetchone()[0].upper() == "TEXT"

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True,
    )
    assert upgrade.returncode == 0, upgrade.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0024_restore_publish_keys"
        )
        assert db.execute(
            "SELECT type FROM pragma_table_info('reconciliation_approvals') "
            "WHERE name = 'expected_delta_cents'"
        ).fetchone()[0].upper() == "BIGINT"
        triggers = {
            row[0] for row in db.execute(
                "SELECT name FROM sqlite_master WHERE type = 'trigger' "
                "AND tbl_name = 'reconciliation_approvals'"
            )
        }
        assert {
            "trg_reconciliation_approvals_no_delete",
            "trg_reconciliation_approvals_immutable_content",
        } <= triggers
        db.execute("SAVEPOINT synthetic_guard_proof")
        db.execute(
            "INSERT INTO reconciliation_approvals "
            "(owner_id, canonical_report, report_format_version, algorithm_version, "
            "report_sha256, signed_token_evidence, preview_cutoff, source_fingerprint, "
            "approving_actor_id, approved_at, approved_source_ids, account_corrections_cents, "
            "before_component_totals_cents, after_component_totals_cents, expected_delta_cents, "
            "backup_evidence_reference, backup_cutoff, rollback_deadline, state) "
            "VALUES ('synthetic-owner', X'7b7d', 2, 'test', 'synthetic-digest', "
            "'synthetic-token', CURRENT_TIMESTAMP, 'synthetic-fingerprint', "
            "'synthetic-owner', CURRENT_TIMESTAMP, '[]', '{}', '{}', '{}', 0, "
            "'synthetic://isolated', CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'approved')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM reconciliation_approvals")
        db.execute("ROLLBACK TO SAVEPOINT synthetic_guard_proof")
        db.execute("RELEASE SAVEPOINT synthetic_guard_proof")

    downgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "downgrade", "0016_approved_conversions"],
        env=env, capture_output=True, text=True,
    )
    assert downgrade.returncode == 0, downgrade.stderr
    with sqlite3.connect(path) as db:
        assert db.execute(
            "SELECT type FROM pragma_table_info('reconciliation_approvals') "
            "WHERE name = 'expected_delta_cents'"
        ).fetchone()[0].upper() == "BIGINT"

def test_0017_refuses_text_correction_when_any_conversion_history_exists(tmp_path):
    path = tmp_path / "nonempty-early-text-0016.db"
    env = _create_applied_0016_database(path)
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO reconciliation_approvals "
            "(owner_id, canonical_report, report_format_version, algorithm_version, "
            "report_sha256, signed_token_evidence, preview_cutoff, source_fingerprint, "
            "approving_actor_id, approved_at, approved_source_ids, account_corrections_cents, "
            "before_component_totals_cents, after_component_totals_cents, expected_delta_cents, "
            "backup_evidence_reference, backup_cutoff, rollback_deadline, state) "
            "VALUES ('synthetic-owner', ?, 2, 'synthetic-v1', ?, 'test-token', "
            "CURRENT_TIMESTAMP, 'synthetic-fingerprint', 'synthetic-owner', "
            "CURRENT_TIMESTAMP, '[]', '{}', '{}', '{}', '42', 'synthetic-backup', "
            "CURRENT_TIMESTAMP, CURRENT_TIMESTAMP, 'approved')",
            (b"{}", "a" * 64),
        )
        db.commit()

    upgrade = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        env=env, capture_output=True, text=True,
    )
    assert upgrade.returncode != 0
    assert "reconciliation_approvals contains conversion history" in upgrade.stderr
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT version_num FROM alembic_version").fetchone()[0] == (
            "0016_approved_conversions"
        )
        assert db.execute(
            "SELECT type FROM pragma_table_info('reconciliation_approvals') "
            "WHERE name = 'expected_delta_cents'"
        ).fetchone()[0].upper() == "TEXT"
        assert db.execute(
            "SELECT expected_delta_cents FROM reconciliation_approvals"
        ).fetchone()[0] == "42"
