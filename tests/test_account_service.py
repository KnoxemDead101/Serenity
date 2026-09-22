"""Tests for services/account_service.py: the account business rules."""

from decimal import Decimal

from schemas.account import AccountCreate
from services import account_service


def make_account(db, name, classification="Personal", balance="0", account_type="Checking"):
    """Small helper so each test reads clearly."""
    data = AccountCreate(
        name=name,
        account_type=account_type,
        classification=classification,
        opening_balance=Decimal(balance),
    )
    return account_service.create_account(db, data)


def test_create_account_stores_cents(db):
    account = make_account(db, "Checking", balance="1250.75")
    assert account.id is not None
    assert account.opening_balance_cents == 125075


def test_current_balance_equals_opening_balance_for_now(db):
    account = make_account(db, "Savings", balance="500")
    assert account_service.calculate_current_balance_cents(account) == 50000


def test_list_accounts_is_alphabetical(db):
    make_account(db, "Zeta")
    make_account(db, "Alpha")
    names = [account.name for account in account_service.list_accounts(db)]
    assert names == ["Alpha", "Zeta"]


def test_totals_with_no_accounts(db):
    totals = account_service.get_account_totals(db)
    assert totals.account_count == 0
    assert totals.total_balance == Decimal("0.00")
    # All four classifications appear even when empty.
    assert set(totals.balance_by_classification) == {"Personal", "Business", "Investment", "Trading"}


def test_totals_add_up_by_classification(db):
    make_account(db, "Checking", "Personal", "1000.00")
    make_account(db, "Credit Card", "Personal", "-250.50", account_type="Credit Card")
    make_account(db, "Business", "Business", "300.25", account_type="Business Checking")

    totals = account_service.get_account_totals(db)

    assert totals.account_count == 3
    assert totals.total_balance == Decimal("1049.75")
    assert totals.balance_by_classification["Personal"] == Decimal("749.50")
    assert totals.balance_by_classification["Business"] == Decimal("300.25")
    assert totals.balance_by_classification["Trading"] == Decimal("0.00")
