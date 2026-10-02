"""Explicit as-of evidence; caller cannot select an owner or change an amount."""

from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

VerificationKind = Literal[
    "account_balance", "debt_balance", "legacy_valuation", "opening_valuation",
]


class VerificationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", hide_input_in_errors=True)
    as_of: date
    evidence: str = Field(min_length=1, max_length=1000)
    snapshot: str = Field(pattern=r"^[0-9a-f]{64}$")

    @field_validator("as_of")
    @classmethod
    def not_future(cls, value):
        if value > datetime.now(timezone.utc).date():
            raise ValueError("As-of date cannot be in the future (UTC)")
        return value

    @field_validator("evidence")
    @classmethod
    def required_evidence(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Evidence is required")
        return value