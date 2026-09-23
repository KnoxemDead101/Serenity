from datetime import date, datetime
from decimal import Decimal

from pydantic import BaseModel, field_validator

from utils.choices import ACCOUNT_CLASSIFICATIONS, TRANSACTION_TYPES
from utils.validators import optional_text, require_choice, require_text, validate_money


class TransactionCreate(BaseModel):
    date: date
    transaction_type: str
    amount: Decimal
    description: str
    classification: str | None = None
    merchant: str | None = None
    location: str | None = None
    category: str | None = None
    subcategory: str | None = None

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
        return None if cleaned is None else require_choice(cleaned, ACCOUNT_CLASSIFICATIONS, "Classification")

    @field_validator("merchant", "location", "category", "subcategory")
    @classmethod
    def check_optional_text(cls, value: str | None) -> str | None:
        return optional_text(value, max_length=100)


class TransactionUpdate(TransactionCreate):
    pass


class TransactionRead(BaseModel):
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
    created_at: datetime
    updated_at: datetime


class TransactionSnapshot(BaseModel):
    date: date
    transaction_type: str
    amount: Decimal
    description: str
    category: str | None
    classification: str | None = None
    merchant: str | None = None
    location: str | None = None
    subcategory: str | None = None


class TransactionCorrectionRead(BaseModel):
    id: int
    transaction_id: int
    action: str
    changed_at: datetime
    before: TransactionSnapshot
    after: TransactionSnapshot | None