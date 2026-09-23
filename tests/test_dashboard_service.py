"""Tests for dashboard aggregation and exact-cent net worth."""

from datetime import date
from decimal import Decimal
from conftest import TEST_OWNER_ID

from schemas.account import AccountCreate
from schemas.finance import DebtCreate, InvestmentCreate
from schemas.transaction import TransactionCreate
from services import account_service, dashboard_service, finance_service, transaction_service


def test_net_worth_formula_in_cents():
    assert dashboard_service.calculate_net_worth_cents(100_010, 25_005, 40_020) == 84_995
    assert dashboard_service.calculate_net_worth_cents(0, 0, 150) == -150


def test_dashboard_net_worth_uses_every_source(db):
    account = account_service.create_account(db, AccountCreate(
        name="Checking", account_type="Checking", classification="Personal",
        opening_balance=Decimal("100.10"),
    ), TEST_OWNER_ID)
    transaction_service.create_transaction(db, account, TransactionCreate(
        date=date(2026, 9, 23), transaction_type="Expense",
        amount=Decimal("0.15"), description="Parking",
    ))
    finance_service.create_investment(db, InvestmentCreate(
        name="Index fund", quantity=Decimal("1"),
        cost_basis=Decimal("10.00"), current_value=Decimal("12.34"),
    ), TEST_OWNER_ID)
    finance_service.create_debt(db, DebtCreate(
        name="Card", debt_type="Credit Card", balance=Decimal("20.02"),
    ), TEST_OWNER_ID)
    summary = dashboard_service.get_dashboard_summary(db, TEST_OWNER_ID)
    assert summary.total_balance == Decimal("99.95")
    assert summary.net_worth == Decimal("92.27")


def test_dashboard_summary_never_counts_another_owner(db):
    account_service.create_account(db, AccountCreate(
        name="Owner A", account_type="Checking", classification="Personal",
        opening_balance=Decimal("100"),
    ), "owner-a")
    summary = dashboard_service.get_dashboard_summary(db, "owner-b")
    assert summary.account_count == 0
    assert summary.total_balance == Decimal("0.00")