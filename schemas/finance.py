from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from utils.choices import BILL_FREQUENCIES, DEBT_TYPES
from utils.validators import optional_text, require_choice, require_text, validate_money


def validate_non_negative_money(value: Decimal, field_name: str) -> Decimal:
    value = validate_money(value, field_name)
    if value < 0:
        raise ValueError(f"{field_name} cannot be negative")
    return value


def validate_rate(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0 or value > Decimal("1000"):
        raise ValueError("Interest rate must be between 0 and 1000")
    if value.quantize(Decimal("0.001")) != value:
        raise ValueError("Interest rate can have at most 3 decimal places")
    return value


def validate_quantity(value: Decimal) -> Decimal:
    if not value.is_finite() or value < 0 or value.quantize(Decimal("0.00000001")) != value:
        raise ValueError("Quantity must be non-negative with at most 8 decimal places")
    return value


class BillCreate(BaseModel):
    name: str
    amount: Decimal
    due_date: date
    frequency: str = "Monthly"
    category: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("amount")
    @classmethod
    def check_amount(cls, value: Decimal) -> Decimal:
        return validate_non_negative_money(value, "Amount")

    @field_validator("frequency")
    @classmethod
    def check_frequency(cls, value: str) -> str:
        return require_choice(value, BILL_FREQUENCIES, "Frequency")

    @field_validator("category")
    @classmethod
    def check_category(cls, value: str | None) -> str | None:
        return optional_text(value, 100)

    @field_validator("notes")
    @classmethod
    def check_notes(cls, value: str | None) -> str | None:
        return optional_text(value, 1000)


class BillRead(BaseModel):
    id: int
    name: str
    amount: Decimal
    due_date: date
    frequency: str
    category: str | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class DebtCreate(BaseModel):
    name: str
    debt_type: str = "Other"
    balance: Decimal
    interest_rate: Decimal = Decimal("0.00")
    minimum_payment: Decimal = Decimal("0.00")
    due_date: date | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("debt_type")
    @classmethod
    def check_debt_type(cls, value: str) -> str:
        return require_choice(value, DEBT_TYPES, "Debt type")

    @field_validator("balance", "minimum_payment")
    @classmethod
    def check_money(cls, value: Decimal, info) -> Decimal:
        return validate_non_negative_money(value, info.field_name.replace("_", " ").title())

    @field_validator("interest_rate")
    @classmethod
    def check_interest_rate(cls, value: Decimal) -> Decimal:
        return validate_rate(value)

    @field_validator("notes")
    @classmethod
    def check_notes(cls, value: str | None) -> str | None:
        return optional_text(value, 1000)


class DebtRead(BaseModel):
    id: int
    name: str
    debt_type: str
    balance: Decimal
    interest_rate: Decimal
    minimum_payment: Decimal
    due_date: date | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class InvestmentCreate(BaseModel):
    name: str
    ticker: str | None = None
    quantity: Decimal = Decimal("0")
    cost_basis: Decimal
    current_value: Decimal
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("ticker")
    @classmethod
    def check_ticker(cls, value: str | None) -> str | None:
        return optional_text(value, 20)

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: Decimal) -> Decimal:
        return validate_quantity(value)

    @field_validator("cost_basis", "current_value")
    @classmethod
    def check_money(cls, value: Decimal, info) -> Decimal:
        return validate_non_negative_money(value, info.field_name.replace("_", " ").title())

    @field_validator("notes")
    @classmethod
    def check_notes(cls, value: str | None) -> str | None:
        return optional_text(value, 1000)


class InvestmentRead(BaseModel):
    id: int
    name: str
    ticker: str | None
    quantity: Decimal
    cost_basis: Decimal
    current_value: Decimal
    notes: str | None
    created_at: datetime
    updated_at: datetime


class FinanceSummary(BaseModel):
    bill_count: int
    monthly_bill_total: Decimal
    debt_count: int
    debt_balance: Decimal
    investment_count: int
    investment_value: Decimal