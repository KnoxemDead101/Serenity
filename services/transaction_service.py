"""Transaction rules, including optional business and dependent labels."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.account import Account, utc_now
from models.business import Business
from models.dependent import Dependent
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from schemas.transaction import (
    TransactionCorrectionRead, TransactionCreate, TransactionRead,
    TransactionSnapshot, TransactionUpdate,
)
from services.ownership import require_owner_id
from utils.money import cents_to_dollars, dollars_to_cents


class TransactionRuleError(ValueError):
    """A database-dependent transaction business rule was violated."""


def signed_amount_cents(transaction: Transaction) -> int:
    if transaction.transaction_type == "Income":
        return transaction.amount_cents
    if transaction.transaction_type == "Expense":
        return -transaction.amount_cents
    raise ValueError(f"Unknown transaction type: {transaction.transaction_type!r}")


def active_balance_change_cents(account: Account) -> int:
    return sum(
        signed_amount_cents(t) for t in account.transactions if t.deleted_at is None
    )


def resolve_classification(account: Account, requested: str | None) -> str:
    return requested if requested is not None else account.classification


def _resolve_business(
    db: Session, business_id: int | None, owner_id: str,
    existing: Transaction | None
) -> Business | None:
    if business_id is None:
        return None
    business = db.scalar(select(Business).where(
        Business.id == business_id, Business.owner_id == owner_id
    ))
    if business is None:
        raise TransactionRuleError("That business doesn't exist.")
    if business.active is None:
        raise TransactionRuleError("Business has no active lifecycle state.")
    if not business.active and not (existing and existing.business_id == business.id):
        raise TransactionRuleError(
            f'"{business.name}" is deactivated. Reactivate it on the Setup page to use it.'
        )
    return business


def _resolve_dependent(
    db: Session, dependent_id: int | None, owner_id: str,
    existing: Transaction | None
) -> Dependent | None:
    if dependent_id is None:
        return None
    dependent = db.scalar(select(Dependent).where(
        Dependent.id == dependent_id, Dependent.owner_id == owner_id
    ))
    if dependent is None:
        raise TransactionRuleError("That dependent doesn't exist.")
    if dependent.active is None:
        raise TransactionRuleError("Dependent has no active lifecycle state.")
    if not dependent.active and not (existing and existing.dependent_id == dependent.id):
        raise TransactionRuleError(
            f'"{dependent.display_name}" is deactivated. Reactivate them on the Setup page to use them.'
        )
    return dependent


def _apply_fields(
    db: Session, transaction: Transaction, account: Account,
    data: TransactionCreate, existing: Transaction | None = None,
) -> None:
    business = _resolve_business(db, data.business_id, account.owner_id, existing)
    dependent = _resolve_dependent(db, data.dependent_id, account.owner_id, existing)
    if business is not None and data.classification not in (None, "Business"):
        raise TransactionRuleError(
            f'A transaction linked to "{business.name}" must be classified as Business.'
        )
    transaction.date = data.date
    transaction.transaction_type = data.transaction_type
    transaction.classification = (
        "Business" if business is not None and data.classification is None
        else resolve_classification(account, data.classification)
    )
    transaction.amount_cents = dollars_to_cents(data.amount)
    transaction.description = data.description
    transaction.merchant = data.merchant
    transaction.location = data.location
    transaction.category = data.category
    transaction.subcategory = data.subcategory
    transaction.business = business
    transaction.dependent = dependent


def create_transaction(db: Session, account: Account, data: TransactionCreate) -> Transaction:
    if account.active is None:
        raise TransactionRuleError("Account has no active lifecycle state.")
    if not account.active:
        raise TransactionRuleError(
            "This account is deactivated. Reactivate it to record new transactions."
        )
    transaction = Transaction(owner_id=require_owner_id(account.owner_id))
    _apply_fields(db, transaction, account, data)
    account.transactions.append(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def list_transactions(
    db: Session, account_id: int, owner_id: str
) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(
        Transaction.account_id == account_id,
        Transaction.owner_id == require_owner_id(owner_id),
        Transaction.deleted_at.is_(None)
    ).order_by(Transaction.date.desc(), Transaction.id.desc())))


def get_transaction(
    db: Session, account_id: int, transaction_id: int,
    owner_id: str,
) -> Transaction | None:
    return db.scalar(select(Transaction).where(
        Transaction.id == transaction_id, Transaction.account_id == account_id,
        Transaction.owner_id == require_owner_id(owner_id),
        Transaction.deleted_at.is_(None)
    ))


def transaction_snapshot(transaction: Transaction) -> dict:
    return {
        "date": transaction.date.isoformat(),
        "transaction_type": transaction.transaction_type,
        "classification": transaction.classification,
        "amount_cents": transaction.amount_cents,
        "description": transaction.description,
        "merchant": transaction.merchant, "location": transaction.location,
        "category": transaction.category, "subcategory": transaction.subcategory,
        "business_id": transaction.business.id if transaction.business else None,
        "business_name": transaction.business.name if transaction.business else None,
        "dependent_id": transaction.dependent.id if transaction.dependent else None,
        "dependent_name": (
            transaction.dependent.display_name if transaction.dependent else None
        ),
    }


def record_correction(db: Session, transaction: Transaction, action: str, before: dict) -> None:
    db.add(TransactionCorrection(
        owner_id=transaction.owner_id, account_id=transaction.account_id,
        transaction_id=transaction.id, action=action,
        changed_at=utc_now(), before=before,
        after=transaction_snapshot(transaction) if action == "Updated" else None,
    ))


def update_transaction(db: Session, transaction: Transaction, data: TransactionUpdate) -> Transaction:
    before = transaction_snapshot(transaction)
    _apply_fields(db, transaction, transaction.account, data, existing=transaction)
    record_correction(db, transaction, "Updated", before)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction: Transaction) -> None:
    before = transaction_snapshot(transaction)
    transaction.deleted_at = utc_now()
    record_correction(db, transaction, "Deleted", before)
    db.commit()


def list_corrections(
    db: Session, account_id: int, owner_id: str
) -> list[TransactionCorrection]:
    return list(db.scalars(select(TransactionCorrection).where(
        TransactionCorrection.account_id == account_id,
        TransactionCorrection.owner_id == require_owner_id(owner_id),
    ).order_by(TransactionCorrection.changed_at.desc(), TransactionCorrection.id.desc())))


def _snapshot_from_json(data: dict) -> TransactionSnapshot:
    return TransactionSnapshot(
        date=data["date"], transaction_type=data["transaction_type"],
        amount=cents_to_dollars(data["amount_cents"]), description=data["description"],
        category=data.get("category"), classification=data.get("classification"),
        merchant=data.get("merchant"), location=data.get("location"),
        subcategory=data.get("subcategory"), business_id=data.get("business_id"),
        business_name=data.get("business_name"), dependent_id=data.get("dependent_id"),
        dependent_name=data.get("dependent_name"),
    )


def to_correction_read(correction: TransactionCorrection) -> TransactionCorrectionRead:
    return TransactionCorrectionRead(
        id=correction.id, transaction_id=correction.transaction_id, action=correction.action,
        changed_at=correction.changed_at, before=_snapshot_from_json(correction.before),
        after=_snapshot_from_json(correction.after) if correction.after is not None else None,
    )


def to_transaction_read(transaction: Transaction) -> TransactionRead:
    return TransactionRead(
        id=transaction.id, account_id=transaction.account_id, date=transaction.date,
        transaction_type=transaction.transaction_type, classification=transaction.classification,
        amount=cents_to_dollars(transaction.amount_cents), description=transaction.description,
        merchant=transaction.merchant, location=transaction.location,
        category=transaction.category, subcategory=transaction.subcategory,
        business_id=transaction.business_id,
        business_name=transaction.business.name if transaction.business else None,
        dependent_id=transaction.dependent_id,
        dependent_name=transaction.dependent.display_name if transaction.dependent else None,
        created_at=transaction.created_at, updated_at=transaction.updated_at,
    )