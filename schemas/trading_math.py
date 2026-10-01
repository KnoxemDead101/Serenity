"""Inputs and calculated outputs for the hypothetical Profit Engine calculator.

This is not a trade record. Financial results are computed on the server and
never written to an account, investment, or transaction.
"""

from decimal import Decimal, localcontext
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator


MAX_INPUT = Decimal("1000000000")
PRICE_STEP = Decimal("0.00000001")
MONEY_STEP = Decimal("0.01")


def bounded_decimal(
    value: Decimal, name: str, *, step: Decimal = PRICE_STEP,
    positive: bool = False, non_negative: bool = False,
) -> Decimal:
    """Validate exact decimals without using ambient Decimal rounding context."""
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    if abs(value) > MAX_INPUT:
        raise ValueError(f"{name} must be at most 1,000,000,000 in magnitude")
    if positive and value <= 0:
        raise ValueError(f"{name} must be positive")
    if non_negative and value < 0:
        raise ValueError(f"{name} cannot be negative")
    with localcontext() as context:
        context.prec = 80
        scaled = value / step
        if scaled != scaled.to_integral_value():
            raise ValueError(
                f"{name} can have at most {-step.as_tuple().exponent} decimal places"
            )
    return value


class CalculationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    specification_id: int
    direction: Literal["LONG", "SHORT"]
    quantity: Decimal
    entry_price: Decimal
    exit_price: Decimal | None = None
    stop_price: Decimal | None = None
    target_price: Decimal | None = None
    fees: Decimal = Decimal("0")

    @field_validator("specification_id")
    @classmethod
    def check_specification_id(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("Specification ID must be positive")
        return value

    @field_validator("quantity")
    @classmethod
    def check_quantity(cls, value: Decimal) -> Decimal:
        return bounded_decimal(value, "Quantity", positive=True)

    @field_validator("entry_price", "exit_price", "stop_price", "target_price")
    @classmethod
    def check_price(cls, value: Decimal | None, info) -> Decimal | None:
        return None if value is None else bounded_decimal(value, info.field_name.replace("_", " ").title())

    @field_validator("fees")
    @classmethod
    def check_fees(cls, value: Decimal) -> Decimal:
        return bounded_decimal(value, "Fees", step=MONEY_STEP, non_negative=True)


class CalculationRead(BaseModel):
    """Decimals serialize as JSON strings; absent computations remain null."""

    price_difference: Decimal | None = None
    points: Decimal | None = None
    ticks: Decimal | None = None
    gross_pnl: Decimal | None = None
    fees: Decimal
    net_pnl: Decimal | None = None
    risk_points: Decimal | None = None
    risk_ticks: Decimal | None = None
    risk_dollars: Decimal | None = None
    reward_points: Decimal | None = None
    reward_ticks: Decimal | None = None
    reward_dollars: Decimal | None = None
    planned_rr: Decimal | None = None
    realized_r: Decimal | None = None