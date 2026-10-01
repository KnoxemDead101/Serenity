"""Instrument metadata only: not holdings, quotes, or recorded trade activity."""

import re
from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from utils.validators import optional_text, require_text

SCALE = Decimal("100000000")
MAX_SPEC_VALUE = Decimal("1000000000")
SYMBOL_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9._/-]{0,29}$")


def spec_units(value: Decimal, label: str) -> int:
    if not value.is_finite() or not (0 < value <= MAX_SPEC_VALUE):
        raise ValueError(f"{label} must be positive and at most 1,000,000,000")
    scaled = value * SCALE
    if scaled != scaled.to_integral_value():
        raise ValueError(f"{label} can have at most 8 decimal places")
    return int(scaled)


class InstrumentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    symbol: str
    name: str
    asset_type: Literal["STOCK", "ETF", "FUTURE"]
    exchange: str | None = None
    currency: Literal["USD"] = "USD"
    tick_size: Decimal = Decimal("0.01")
    point_value: Decimal = Decimal("1")

    @field_validator("symbol")
    @classmethod
    def validate_symbol(cls, value: str) -> str:
        value = require_text(value, "Symbol", 30).upper()
        if not SYMBOL_PATTERN.fullmatch(value):
            raise ValueError("Symbol must contain letters, digits, '.', '_', '/' or '-'")
        return value

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("exchange")
    @classmethod
    def validate_exchange(cls, value: str | None) -> str | None:
        return optional_text(value, 100)

    @field_validator("tick_size", "point_value")
    @classmethod
    def validate_scaled(cls, value: Decimal, info) -> Decimal:
        spec_units(value, info.field_name.replace("_", " ").title())
        return value

    @model_validator(mode="after")
    def validate_equity_value(self):
        if self.asset_type in ("STOCK", "ETF") and self.point_value != 1:
            raise ValueError("Stock and ETF point value must be 1")
        if self.asset_type == "FUTURE" and not {"tick_size", "point_value"} <= self.model_fields_set:
            raise ValueError("Futures require explicit tick size and point value; do not assume $1 per point")
        return self


class InstrumentUpdate(InstrumentCreate):
    """Full replacement of metadata; existing specification remains immutable."""


class InstrumentRead(BaseModel):
    id: int
    specification_id: int
    version: int
    symbol: str
    name: str
    asset_type: str
    exchange: str | None
    currency: str
    tick_size: Decimal
    point_value: Decimal
    active: bool
    created_at: datetime
    updated_at: datetime