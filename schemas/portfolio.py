"""Only organizational metadata; no balances or client-selected owner IDs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from utils.validators import optional_text, require_text


class PortfolioWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        return require_text(value, "Name", 100)

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, value: str | None) -> str | None:
        return optional_text(value, 1000)


class PortfolioRead(PortfolioWrite):
    id: int
    active: bool
    created_at: datetime
    updated_at: datetime


class InvestmentAccountWrite(PortfolioWrite):
    portfolio_id: int
    account_id: int


class InvestmentAccountRead(InvestmentAccountWrite):
    id: int
    active: bool
    created_at: datetime
    updated_at: datetime