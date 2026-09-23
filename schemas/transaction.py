"""
Transaction schemas: what the API accepts and returns for transactions.

models/transaction.py  -> how a transaction is STORED (cents, columns)
schemas/transaction.py -> what the API ACCEPTS and RETURNS (dollars, checks)

These used to live in schemas/account.py. They moved here so each file
has one job, matching the v0.2 rule "no giant all-in-one modules".
"""

from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from schemas.timestamps import TimestampReadModel
from utils.choices import ACCOUNT_CLASSIFICATIONS, TRANSACTION_TYPES
from utils.validators import optional_text, require_choice, require_text, validate_money


class TransactionCreate(BaseModel):
    """Validated transaction data accepted by the API."""
    date: date
    transaction_type: str
    amount: Decimal
    description: str
    classification: str | None = None
    merchant: str | None = None
    location: str | None = None
    category: str | None = None
    subcategory: str | None = None
    business_id: int | None = None
    dependent_id: int | None = None

    @field_validator("transaction_type")
    @classmethod
    def check_transaction_type(cls, value: str) -> str:
        return require_choice(value, TRANSACTION_TYPES, "Transaction type")

    @field_validator("amount")
    @classmethod
    def check_amount(cls, value: Decimal) -> Decimal:
        amount = validate_money(value, "Amount")
        if amount <= 0:
            raise ValueError("Amount must be greater than zero")
        return amount

    @field_validator("description")
    @classmethod
    def check_description(cls, value: str) -> str:
        return require_text(value, "Description", max_length=200)

    @field_validator("classification")
    @classmethod
    def check_classification(cls, value: str | None) -> str | None:
        cleaned = optional_text(value, max_length=50)
        if cleaned is None:
            return None
        return require_choice(cleaned, ACCOUNT_CLASSIFICATIONS, "Classification")

    @field_validator("merchant", "location", "category", "subcategory")
    @classmethod
    def check_optional_text(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=100)


class TransactionUpdate(TransactionCreate):
    """Editable transaction fields; account ownership cannot change."""


class TransactionRead(TimestampReadModel):
    id: int
    account_id: int
    date: date
    transaction_type: str
    classification: str
    amount: Decimal
    description: str
    merchant: str | None
    location: str | None
    category: str | None
    subcategory: str | None
    business_id: int | None
    business_name: str | None
    dependent_id: int | None
    dependent_name: str | None
    created_at: datetime
    updated_at: datetime


class TransactionSnapshot(BaseModel):
    """
    A frozen copy of a transaction at one moment (used by the history).

    The newer fields are optional because snapshots saved before this
    change don't contain them, and history is never rewritten.
    """
    date: date
    transaction_type: str
    amount: Decimal
    description: str
    category: str | None
    classification: str | None = None
    merchant: str | None = None
    location: str | None = None
    subcategory: str | None = None
    business_id: int | None = None
    business_name: str | None = None
    dependent_id: int | None = None
    dependent_name: str | None = None


class TransactionCorrectionRead(TimestampReadModel):
    id: int
    transaction_id: int
    action: str
    changed_at: datetime
    before: TransactionSnapshot
    after: TransactionSnapshot | None