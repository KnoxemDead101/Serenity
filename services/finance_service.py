"""
Finance service: bills, debts and (temporary) investments.

    api/finance.py -> services/finance_service.py -> database

Each "total_..._cents" function below is the ONE formula for that total.
The finance summary and the dashboard's net worth both call them, so the
same number can never be calculated two different ways.
"""

from collections.abc import Iterable

from sqlalchemy import inspect, select
from sqlalchemy.orm import Session

from models.bill import Bill
from models.debt import Debt
from models.investment import Investment
from schemas.finance import (
    BillCreate,
    BillRead,
    BillUpdate,
    DebtCreate,
    DebtRead,
    DebtUpdate,
    FinanceSummary,
    InvestmentCreate,
    InvestmentRead,
    InvestmentUpdate,
)
from utils.choices import BILL_FREQUENCIES, DEBT_TYPES
from utils.money import (
    cents_to_dollars,
    dollars_to_cents,
    milli_to_percent,
    percent_to_milli,
    quantity_to_units,
    round_half_up_division,
    units_to_quantity,
)


def is_active(record: Bill | Debt | Investment) -> bool:
    """New unsaved records use the true default; persisted NULLs are invalid."""
    if record.active is None:
        if inspect(record).transient:
            return True
        raise ValueError(f"{type(record).__name__} has no active lifecycle state")
    return record.active


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

def create_bill(db: Session, data: BillCreate) -> Bill:
    bill = Bill(
        name=data.name,
        amount_cents=dollars_to_cents(data.amount),
        due_date=data.due_date,
        frequency=data.frequency,
        category=data.category,
        notes=data.notes,
    )
    db.add(bill)
    db.commit()
    db.refresh(bill)
    return bill


def list_bills(db: Session) -> list[Bill]:
    return list(db.scalars(select(Bill).order_by(Bill.due_date, Bill.name)))


def get_bill(db: Session, bill_id: int) -> Bill | None:
    return db.get(Bill, bill_id)


def update_bill(db: Session, bill: Bill, data: BillUpdate) -> Bill:
    bill.name = data.name
    bill.amount_cents = dollars_to_cents(data.amount)
    bill.due_date = data.due_date
    bill.frequency = data.frequency
    bill.category = data.category
    bill.notes = data.notes
    db.commit()
    db.refresh(bill)
    return bill


def set_bill_active(db: Session, bill: Bill, active: bool) -> Bill:
    bill.active = active
    db.commit()
    db.refresh(bill)
    return bill


def to_bill_read(bill: Bill) -> BillRead:
    return BillRead(
        id=bill.id,
        name=bill.name,
        amount=cents_to_dollars(bill.amount_cents),
        due_date=bill.due_date,
        frequency=bill.frequency,
        category=bill.category,
        notes=bill.notes,
        active=bill.active,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
    )


# ---------------------------------------------------------------------------
# Debts
# ---------------------------------------------------------------------------

def create_debt(db: Session, data: DebtCreate) -> Debt:
    debt = Debt(
        name=data.name,
        debt_type=data.debt_type,
        balance_cents=dollars_to_cents(data.balance),
        interest_rate_milli=percent_to_milli(data.interest_rate),
        minimum_payment_cents=dollars_to_cents(data.minimum_payment),
        due_date=data.due_date,
        notes=data.notes,
    )
    db.add(debt)
    db.commit()
    db.refresh(debt)
    return debt


def list_debts(db: Session) -> list[Debt]:
    return list(db.scalars(select(Debt).order_by(Debt.balance_cents.desc(), Debt.name)))


def get_debt(db: Session, debt_id: int) -> Debt | None:
    return db.get(Debt, debt_id)


def update_debt(db: Session, debt: Debt, data: DebtUpdate) -> Debt:
    debt.name = data.name
    debt.debt_type = data.debt_type
    debt.balance_cents = dollars_to_cents(data.balance)
    debt.interest_rate_milli = percent_to_milli(data.interest_rate)
    debt.minimum_payment_cents = dollars_to_cents(data.minimum_payment)
    debt.due_date = data.due_date
    debt.notes = data.notes
    db.commit()
    db.refresh(debt)
    return debt


def set_debt_active(db: Session, debt: Debt, active: bool) -> Debt:
    debt.active = active
    db.commit()
    db.refresh(debt)
    return debt


def to_debt_read(debt: Debt) -> DebtRead:
    return DebtRead(
        id=debt.id,
        name=debt.name,
        debt_type=debt.debt_type,
        balance=cents_to_dollars(debt.balance_cents),
        interest_rate=milli_to_percent(debt.interest_rate_milli),
        minimum_payment=cents_to_dollars(debt.minimum_payment_cents),
        due_date=debt.due_date,
        notes=debt.notes,
        active=debt.active,
        created_at=debt.created_at,
        updated_at=debt.updated_at,
    )


# ---------------------------------------------------------------------------
# Investments (temporary starting-position model)
# ---------------------------------------------------------------------------

def create_investment(db: Session, data: InvestmentCreate) -> Investment:
    investment = Investment(
        name=data.name,
        ticker=data.ticker.upper() if data.ticker else None,
        quantity_units=quantity_to_units(data.quantity),
        cost_basis_cents=dollars_to_cents(data.cost_basis),
        current_value_cents=dollars_to_cents(data.current_value),
        notes=data.notes,
    )
    db.add(investment)
    db.commit()
    db.refresh(investment)
    return investment


def list_investments(db: Session) -> list[Investment]:
    return list(db.scalars(select(Investment).order_by(Investment.name)))


def get_investment(db: Session, investment_id: int) -> Investment | None:
    return db.get(Investment, investment_id)


def update_investment(
    db: Session, investment: Investment, data: InvestmentUpdate
) -> Investment:
    investment.name = data.name
    investment.ticker = data.ticker.upper() if data.ticker else None
    investment.quantity_units = quantity_to_units(data.quantity)
    investment.cost_basis_cents = dollars_to_cents(data.cost_basis)
    investment.current_value_cents = dollars_to_cents(data.current_value)
    investment.notes = data.notes
    db.commit()
    db.refresh(investment)
    return investment


def set_investment_active(db: Session, investment: Investment, active: bool) -> Investment:
    investment.active = active
    db.commit()
    db.refresh(investment)
    return investment


def to_investment_read(investment: Investment) -> InvestmentRead:
    return InvestmentRead(
        id=investment.id,
        name=investment.name,
        ticker=investment.ticker,
        quantity=units_to_quantity(investment.quantity_units),
        cost_basis=cents_to_dollars(investment.cost_basis_cents),
        current_value=cents_to_dollars(investment.current_value_cents),
        notes=investment.notes,
        active=investment.active,
        created_at=investment.created_at,
        updated_at=investment.updated_at,
    )


def total_debt_balance_cents(debts: Iterable[Debt]) -> int:
    """Everything owed across active debts, in cents."""
    return sum(debt.balance_cents for debt in debts if is_active(debt))


def total_investment_value_cents(investments: Iterable[Investment]) -> int:
    """Current value of the given investments, in cents (not cost basis)."""
    return sum(
        investment.current_value_cents
        for investment in investments
        if is_active(investment)
    )


def normalized_monthly_bill_total_cents(bills: Iterable[Bill]) -> int:
    """
    Normalize recurring bills to one monthly total and round once.

    Monthly bills contribute 12/12, quarterly bills 4/12, annual bills
    1/12, and one-time bills are excluded from the recurring total.
    All twelfths are added before rounding once, preventing per-bill
    rounding drift.
    """
    twelfths_of_a_cent = 0
    for bill in bills:
        if not is_active(bill):
            continue
        if bill.frequency == "Monthly":
            twelfths_of_a_cent += bill.amount_cents * 12
        elif bill.frequency == "Quarterly":
            twelfths_of_a_cent += bill.amount_cents * 4
        elif bill.frequency == "Annual":
            twelfths_of_a_cent += bill.amount_cents
    return round_half_up_division(twelfths_of_a_cent, 12)


# ---------------------------------------------------------------------------
# Summary and options
# ---------------------------------------------------------------------------

def get_finance_summary(db: Session) -> FinanceSummary:
    bills = list_bills(db)
    debts = list_debts(db)
    investments = list_investments(db)

    return FinanceSummary(
        bill_count=sum(1 for bill in bills if is_active(bill)),
        monthly_bill_total=cents_to_dollars(
            normalized_monthly_bill_total_cents(bills)
        ),
        debt_count=sum(1 for debt in debts if is_active(debt)),
        debt_balance=cents_to_dollars(total_debt_balance_cents(debts)),
        investment_count=sum(1 for investment in investments if is_active(investment)),
        investment_value=cents_to_dollars(
            total_investment_value_cents(investments)
        ),
    )


def get_finance_options() -> dict[str, list[str]]:
    return {
        "bill_frequencies": BILL_FREQUENCIES,
        "debt_types": DEBT_TYPES,
    }