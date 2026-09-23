from decimal import Decimal

import pytest

from models.bill import Bill
from schemas.finance import DebtCreate, InvestmentCreate
from services import finance_service
from conftest import TEST_OWNER_ID
from services.ownership import MissingOwnerError


def test_monthly_bill_normalization_rounds_once():
    bills = [
        Bill(name=f"Quarterly {number}", amount_cents=10_000, frequency="Quarterly")
        for number in range(3)
    ]
    assert finance_service.normalized_monthly_bill_total_cents(bills) == 10_000


def test_annual_bill_rounds_half_up_and_one_time_is_excluded():
    bills = [
        Bill(name="Annual", amount_cents=100, frequency="Annual"),
        Bill(name="One-time", amount_cents=50_000, frequency="One-time"),
    ]
    assert finance_service.normalized_monthly_bill_total_cents(bills) == 8


def test_precise_interest_rate_round_trip(db):
    debt = finance_service.create_debt(
        db,
        DebtCreate(
            name="Rewards card",
            debt_type="Credit Card",
            balance=Decimal("1200.00"),
            interest_rate=Decimal("6.875"),
            minimum_payment=Decimal("50.00"),
        ),
        TEST_OWNER_ID,
    )
    result = finance_service.to_debt_read(debt)
    assert result.interest_rate == Decimal("6.875")
    assert result.debt_type == "Credit Card"


def test_four_decimal_interest_rate_is_rejected():
    with pytest.raises(ValueError):
        DebtCreate(
            name="Loan",
            balance=Decimal("10.00"),
            interest_rate=Decimal("6.8751"),
        )


def test_fractional_investment_quantity_round_trip(db):
    investment = finance_service.create_investment(
        db,
        InvestmentCreate(
            name="Fractional fund",
            ticker="VTI",
            quantity=Decimal("0.12345678"),
            cost_basis=Decimal("10.00"),
            current_value=Decimal("12.00"),
        ),
        TEST_OWNER_ID,
    )
    result = finance_service.to_investment_read(investment)
    assert result.quantity == Decimal("0.12345678")


def test_finance_service_reads_require_an_owner(db):
    with pytest.raises(TypeError):
        finance_service.list_bills(db)  # type: ignore[call-arg]
    with pytest.raises(MissingOwnerError):
        finance_service.list_debts(db, " ")