"""All stored cents must fit the amounts accepted by the API."""

import importlib
import pkgutil
import sqlite3
import subprocess
import sys
import os
from decimal import Decimal

import pytest
from pydantic import ValidationError
from sqlalchemy import BigInteger

import models
from schemas.account import AccountCreate
from schemas.finance import InvestmentCreate
from schemas.income_profile import IncomeProfileCreate
from storage.database import Base
from utils.validators import MAX_MONEY, validate_money

money_migration = importlib.import_module("migrations.versions.0013_money_bigint")


def test_every_mapped_cent_field_is_bigint_and_in_migration():
    for module in pkgutil.iter_modules(models.__path__):
        importlib.import_module(f"models.{module.name}")
    mapped = {
        (table.name, column.name)
        for table in Base.metadata.tables.values()
        for column in table.columns
        if column.name.endswith("_cents")
    }
    migrated = {
        (table, column)
        for table, columns in money_migration.MONEY_COLUMNS.items()
        for column in columns
    }
    assert len(mapped) == 11
    assert mapped == migrated
    for table, column in mapped:
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