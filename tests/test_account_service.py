"""Tests for account and transaction business rules (the service layer)."""

from decimal import Decimal
from datetime import date
from conftest import TEST_OWNER_ID

import pytest

from models.transaction import Transaction
from schemas.account import AccountCreate
from schemas.transaction import TransactionCreate
from services import account_service, transaction_service
from services.ownership import MissingOwnerError


def make_account(db, name, classification="Personal", balance="0", account_type="Checking"):
    """Small helper so each test reads clearly."""
    data = AccountCreate(
        name=name,
        account_type=account_type,
        classification=classification,
        opening_balance=Decimal(balance),
    )
    return account_service.create_account(db, data, TEST_OWNER_ID)


def record(db, account, transaction_type, amount, description, day=20, **extra):
    return transaction_service.create_transaction(
        db, account, TransactionCreate(
            date=date(2026, 9, day), transaction_type=transaction_type,
            amount=Decimal(amount), description=description, **extra,
        )
    )


def test_create_account_stores_cents(db):
    account = make_account(db, "Checking", balance="1250.75")
    assert account.id is not None
    assert account.opening_balance_cents == 125075


def test_owner_id_is_mandatory_for_service_operations(db):
    data = AccountCreate(
        name="Checking", account_type="Checking", classification="Personal",
        opening_balance=Decimal("0"),
    )
    with pytest.raises(TypeError):
        account_service.list_accounts(db)  # type: ignore[call-arg]
    with pytest.raises(MissingOwnerError):
        account_service.create_account(db, data, " ")
    with pytest.raises(MissingOwnerError):
        account_service.create_account(db, data, None)  # type: ignore[arg-type]
    with pytest.raises(MissingOwnerError):
        account_service.create_account(db, data, "x" * 256)


def test_current_balance_equals_opening_balance_without_transactions(db):
    account = make_account(db, "Savings", balance="500")
    assert account_service.calculate_current_balance_cents(account) == 50000


def test_transactions_change_balances_in_exact_cents(db):
    account = make_account(db, "Checking", balance="100.10")
    record(db, account, "Income", "0.20", "Refund")
    record(db, account, "Expense", "25.05", "Groceries", day=21)
    assert account_service.calculate_current_balance_cents(account) == 7525
    assert account_service.to_account_read(account).current_balance == Decimal("75.25")
    assert account_service.get_account_totals(db, TEST_OWNER_ID).total_balance == Decimal("75.25")
    assert account_service.get_account_totals(db, TEST_OWNER_ID).balance_by_classification["Personal"] == Decimal("75.25")


def test_signed_amount_is_the_only_place_direction_is_decided():
    assert transaction_service.signed_amount_cents(
        Transaction(transaction_type="Income", amount_cents=500)) == 500
    assert transaction_service.signed_amount_cents(
        Transaction(transaction_type="Expense", amount_cents=500)) == -500
    with pytest.raises(ValueError):
        transaction_service.signed_amount_cents(
            Transaction(transaction_type="Deposit", amount_cents=500))


def test_classification_falls_back_to_account(db):
    account = make_account(db, "KTT Checking", classification="Business",
                           account_type="Business Checking")
    default = record(db, account, "Expense", "10.00", "Postage")
    chosen = record(db, account, "Expense", "10.00", "Personal lunch",
                    classification="Personal")
    assert default.classification == "Business"
    assert chosen.classification == "Personal"


def test_transactions_sorted_newest_first_with_id_tiebreaker(db):
    account = make_account(db, "Checking")
    for day, name in [(20, "old"), (21, "first"), (21, "second")]:
        record(db, account, "Income", "1.00", name, day=day)
    assert [t.description for t in transaction_service.list_transactions(db, account.id, TEST_OWNER_ID)] == [
        "second", "first", "old"
    ]


def test_list_accounts_is_alphabetical(db):
    make_account(db, "Zeta")
    make_account(db, "Alpha")
    names = [account.name for account in account_service.list_accounts(db, TEST_OWNER_ID)]
    assert names == ["Alpha", "Zeta"]


def test_totals_with_no_accounts(db):
    totals = account_service.get_account_totals(db, TEST_OWNER_ID)
    assert totals.account_count == 0
    assert totals.total_balance == Decimal("0.00")
    # All four classifications appear even when empty.
    assert set(totals.balance_by_classification) == {"Personal", "Business", "Investment", "Trading"}


def test_totals_add_up_by_classification(db):
    make_account(db, "Checking", "Personal", "1000.00")
    make_account(db, "Business", "Business", "300.25", account_type="Business Checking")

    totals = account_service.get_account_totals(db, TEST_OWNER_ID)

    assert totals.account_count == 2
    assert totals.total_balance == Decimal("1300.25")
    assert totals.balance_by_classification["Personal"] == Decimal("1000.00")
    assert totals.balance_by_classification["Business"] == Decimal("300.25")
    assert totals.balance_by_classification["Trading"] == Decimal("0.00")
