from collections.abc import Iterable
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.bill import Bill
from models.debt import Debt
from models.investment import Investment
from schemas.finance import (
    BillCreate,
    BillRead,
    DebtCreate,
    DebtRead,
    FinanceSummary,
    InvestmentCreate,
    InvestmentRead,
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


def to_bill_read(bill: Bill) -> BillRead:
    return BillRead(
        id=bill.id,
        name=bill.name,
        amount=cents_to_dollars(bill.amount_cents),
        due_date=bill.due_date,
        frequency=bill.frequency,
        category=bill.category,
        notes=bill.notes,
        created_at=bill.created_at,
        updated_at=bill.updated_at,
    )


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
        created_at=debt.created_at,
        updated_at=debt.updated_at,
    )


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


def to_investment_read(investment: Investment) -> InvestmentRead:
    return InvestmentRead(
        id=investment.id,
        name=investment.name,
        ticker=investment.ticker,
        quantity=units_to_quantity(investment.quantity_units),
        cost_basis=cents_to_dollars(investment.cost_basis_cents),
        current_value=cents_to_dollars(investment.current_value_cents),
        notes=investment.notes,
        created_at=investment.created_at,
        updated_at=investment.updated_at,
    )


def _sum_cents(items: Iterable[int]) -> int:
    return sum(items, 0)


def normalized_monthly_bill_total_cents(bills: Iterable[Bill]) -> int:
    """
    Normalize recurring bills to one monthly total and round once.

    Monthly bills contribute 12/12, quarterly bills 4/12, annual bills
    1/12, and one-time bills are excluded from the recurring total.
    """
    twelfths_of_a_cent = 0
    for bill in bills:
        if bill.frequency == "Monthly":
            twelfths_of_a_cent += bill.amount_cents * 12
        elif bill.frequency == "Quarterly":
            twelfths_of_a_cent += bill.amount_cents * 4
        elif bill.frequency == "Annual":
            twelfths_of_a_cent += bill.amount_cents
    return round_half_up_division(twelfths_of_a_cent, 12)


def get_finance_summary(db: Session) -> FinanceSummary:
    bills = list_bills(db)
    debts = list_debts(db)
    investments = list_investments(db)

    return FinanceSummary(
        bill_count=len(bills),
        monthly_bill_total=cents_to_dollars(
            normalized_monthly_bill_total_cents(bills)
        ),
        debt_count=len(debts),
        debt_balance=cents_to_dollars(_sum_cents(debt.balance_cents for debt in debts)),
        investment_count=len(investments),
        investment_value=cents_to_dollars(
            _sum_cents(investment.current_value_cents for investment in investments)
        ),
    )


def get_finance_options() -> dict[str, list[str]]:
    return {
        "bill_frequencies": BILL_FREQUENCIES,
        "debt_types": DEBT_TYPES,
    }