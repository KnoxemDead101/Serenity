"""
Account schemas: the shape of data going IN and OUT of the API.

models/account.py  -> how an account is STORED (database columns, cents)
schemas/account.py -> what the API ACCEPTS and RETURNS (dollars, checks)

Keeping these separate means the database can change without changing
what the frontend sees, and vice versa.

Pydantic runs the validators automatically. If one raises ValueError,
FastAPI responds with HTTP 422 and a message explaining which field
was wrong. Our route code never runs with bad data.
"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from schemas.timestamps import TimestampReadModel
from utils.choices import ACCOUNT_CLASSIFICATIONS, ACCOUNT_TYPES
from utils.validators import optional_text, require_choice, require_text, validate_money


class AccountCreate(BaseModel):
    """What the client must send to create an account."""

    name: str
    account_type: str
    classification: str
    # Decimal, never float. Negative is allowed (e.g. an overdrawn account).
    opening_balance: Decimal = Decimal("0.00")
    institution: str | None = None
    notes: str | None = None

    @field_validator("name")
    @classmethod
    def check_name(cls, value: str) -> str:
        return require_text(value, "Name")

    @field_validator("account_type")
    @classmethod
    def check_account_type(cls, value: str) -> str:
        return require_choice(value, ACCOUNT_TYPES, "Account type")

    @field_validator("classification")
    @classmethod
    def check_classification(cls, value: str) -> str:
        return require_choice(value, ACCOUNT_CLASSIFICATIONS, "Classification")

    @field_validator("opening_balance")
    @classmethod
    def check_opening_balance(cls, value: Decimal) -> Decimal:
        return validate_money(value, "Opening balance")

    @field_validator("institution")
    @classmethod
    def check_institution(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=100)

    @field_validator("notes")
    @classmethod
    def check_notes(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=1000)


class AccountRead(TimestampReadModel):
    """What the API sends back for one account."""

    id: int
    name: str
    account_type: str
    classification: str
    opening_balance: Decimal
    current_balance: Decimal
    institution: str | None
    notes: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class AccountUpdate(AccountCreate):
    """Full replacement payload for editing an account."""


class AccountTotals(BaseModel):
    """Summary numbers for the dashboard."""

    account_count: int
    total_balance: Decimal
    balance_by_classification: dict[str, Decimal]
