"""Validated request and response models for owner-scoped income plans."""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator, model_validator

from schemas.timestamps import TimestampReadModel
from utils.choices import ACCOUNT_CLASSIFICATIONS, INCOME_TYPES, PAY_FREQUENCIES
from utils.validators import optional_text, require_choice, require_text, validate_money

MAX_INCOME = Decimal("20000000")
MAX_HOURS = Decimal("168")
TYPE_FIELDS = {
    "Hourly": {"hourly_rate", "standard_hours_per_week", "expected_hours_per_week"},
    "Salary": {"annual_salary"},
    "Recurring": {"amount_per_period"},
    "Other": {"amount_per_period"},
    "Variable": {"amount_per_period"},
}
TYPE_REQUIRED = {
    "Hourly": {"hourly_rate": "Hourly rate", "expected_hours_per_week": "Expected hours per week"},
    "Salary": {"annual_salary": "Annual salary"},
    "Recurring": {"amount_per_period": "Amount per paycheck"},
    "Other": {"amount_per_period": "Amount per paycheck"},
    "Variable": {},
}
MONEY_FIELDS = (
    "hourly_rate", "annual_salary", "amount_per_period", "expected_net_per_period"
)
HOUR_FIELDS = ("standard_hours_per_week", "expected_hours_per_week")
TYPE_SPECIFIC_FIELDS = {
    "hourly_rate",
    "standard_hours_per_week",
    "expected_hours_per_week",
    "annual_salary",
    "amount_per_period",
}


def _positive_money(value: Decimal | None, name: str) -> Decimal | None:
    if value is None:
        return None
    value = validate_money(value, name)
    if value <= 0 or value > MAX_INCOME:
        raise ValueError(f"{name} must be more than 0 and at most 20,000,000")
    return value


def _hours(value: Decimal | None, name: str) -> Decimal | None:
    if value is None:
        return None
    if not value.is_finite() or value <= 0 or value > MAX_HOURS:
        raise ValueError(f"{name} must be more than 0 and at most 168")
    if value.quantize(Decimal("0.01")) != value:
        raise ValueError(f"{name} can have at most 2 decimal places")
    return value


class IncomeProfileCreate(BaseModel):
    name: str
    income_type: str
    classification: str = "Personal"
    pay_frequency: str | None = None
    hourly_rate: Decimal | None = None
    standard_hours_per_week: Decimal | None = None
    expected_hours_per_week: Decimal | None = None
    annual_salary: Decimal | None = None
    amount_per_period: Decimal | None = None
    expected_net_per_period: Decimal | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return require_text(value, "Name", max_length=100)

    @field_validator("income_type")
    @classmethod
    def validate_type(cls, value: str) -> str:
        return require_choice(value, INCOME_TYPES, "Income type")

    @field_validator("classification")
    @classmethod
    def validate_classification(cls, value: str) -> str:
        return require_choice(value, ACCOUNT_CLASSIFICATIONS, "Classification")

    @field_validator("pay_frequency", mode="before")
    @classmethod
    def validate_frequency(cls, value):
        if value is None or (isinstance(value, str) and not value.strip()):
            return None
        return require_choice(value, PAY_FREQUENCIES, "Pay frequency")

    @field_validator(
        "hourly_rate", "standard_hours_per_week", "expected_hours_per_week",
        "annual_salary", "amount_per_period", "expected_net_per_period", mode="before",
    )
    @classmethod
    def blank_is_none(cls, value):
        return None if isinstance(value, str) and not value.strip() else value

    @field_validator(*MONEY_FIELDS)
    @classmethod
    def validate_money_values(cls, value, info):
        return _positive_money(value, info.field_name.replace("_", " ").title())

    @field_validator(*HOUR_FIELDS)
    @classmethod
    def validate_hour_values(cls, value, info):
        return _hours(value, info.field_name.replace("_", " ").title())

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return optional_text(value, 1000)

    @model_validator(mode="before")
    @classmethod
    def clear_inapplicable_values(cls, values):
        if isinstance(values, dict) and values.get("income_type") in TYPE_FIELDS:
            values = dict(values)
            allowed = TYPE_FIELDS[values["income_type"]]
            for field in TYPE_SPECIFIC_FIELDS - allowed:
                values[field] = None
        return values

    @model_validator(mode="after")
    def validate_required_values(self):
        missing = [
            label for field, label in TYPE_REQUIRED[self.income_type].items()
            if getattr(self, field) is None
        ]
        if missing:
            raise ValueError(f"{self.income_type} income needs: {', '.join(missing)}")
        if self.income_type != "Variable" and self.pay_frequency is None:
            raise ValueError(f"{self.income_type} income needs a pay frequency")
        if self.expected_net_per_period is not None and self.pay_frequency is None:
            raise ValueError("Expected take-home per paycheck needs a pay frequency")
        return self


class IncomeProfileUpdate(IncomeProfileCreate):
    """Full replacement update request."""


class IncomeCalculation(BaseModel):
    projected: bool
    basis: str
    gross_per_period: Decimal | None
    gross_weekly: Decimal | None
    gross_monthly: Decimal | None
    gross_annual: Decimal | None
    standard_weekly_gross: Decimal | None
    net_per_period: Decimal | None
    net_monthly: Decimal | None
    net_annual: Decimal | None


class IncomeProfileRead(TimestampReadModel):
    id: int
    name: str
    income_type: str
    classification: str
    pay_frequency: str | None
    hourly_rate: Decimal | None
    standard_hours_per_week: Decimal | None
    expected_hours_per_week: Decimal | None
    annual_salary: Decimal | None
    amount_per_period: Decimal | None
    expected_net_per_period: Decimal | None
    notes: str | None
    active: bool
    calculated: IncomeCalculation
    created_at: datetime
    updated_at: datetime


class IncomeSummary(BaseModel):
    active_count: int
    projected_count: int
    variable_count: int
    gross_monthly: Decimal
    gross_annual: Decimal
    net_profile_count: int
    net_monthly: Decimal | None
    net_annual: Decimal | None
    net_is_partial: bool