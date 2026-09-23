"""Transaction business rules, persistence, and correction history."""

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.account import Account, utc_now
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from schemas.transaction import (
    TransactionCorrectionRead, TransactionCreate, TransactionRead,
    TransactionSnapshot, TransactionUpdate,
)
from utils.money import cents_to_dollars, dollars_to_cents


def signed_amount_cents(transaction: Transaction) -> int:
    if transaction.transaction_type == "Income":
        return transaction.amount_cents
    if transaction.transaction_type == "Expense":
        return -transaction.amount_cents
    raise ValueError(f"Unknown transaction type: {transaction.transaction_type!r}")


def active_balance_change_cents(account: Account) -> int:
    return sum(signed_amount_cents(t) for t in account.transactions if t.deleted_at is None)


def resolve_classification(account: Account, requested: str | None) -> str:
    return requested or account.classification


def _apply_fields(transaction: Transaction, account: Account, data: TransactionCreate) -> None:
    transaction.date = data.date
    transaction.transaction_type = data.transaction_type
    transaction.classification = resolve_classification(account, data.classification)
    transaction.amount_cents = dollars_to_cents(data.amount)
    transaction.description = data.description
    transaction.merchant = data.merchant
    transaction.location = data.location
    transaction.category = data.category
    transaction.subcategory = data.subcategory


def create_transaction(db: Session, account: Account, data: TransactionCreate) -> Transaction:
    transaction = Transaction()
    _apply_fields(transaction, account, data)
    account.transactions.append(transaction)
    db.commit()
    db.refresh(transaction)
    return transaction


def list_transactions(db: Session, account_id: int) -> list[Transaction]:
    return list(db.scalars(select(Transaction).where(
        Transaction.account_id == account_id, Transaction.deleted_at.is_(None)
    ).order_by(Transaction.date.desc(), Transaction.id.desc())))


def get_transaction(db: Session, account_id: int, transaction_id: int) -> Transaction | None:
    return db.scalar(select(Transaction).where(
        Transaction.id == transaction_id, Transaction.account_id == account_id,
        Transaction.deleted_at.is_(None)
    ))


def transaction_snapshot(transaction: Transaction) -> dict:
    return {
        "date": transaction.date.isoformat(), "transaction_type": transaction.transaction_type,
        "classification": transaction.classification, "amount_cents": transaction.amount_cents,
        "description": transaction.description, "merchant": transaction.merchant,
        "location": transaction.location, "category": transaction.category,
        "subcategory": transaction.subcategory,
    }


def record_correction(db: Session, transaction: Transaction, action: str, before: dict) -> None:
    db.add(TransactionCorrection(
        account_id=transaction.account_id, transaction_id=transaction.id, action=action,
        changed_at=utc_now(), before=before,
        after=transaction_snapshot(transaction) if action == "Updated" else None,
    ))


def update_transaction(db: Session, transaction: Transaction, data: TransactionUpdate) -> Transaction:
    before = transaction_snapshot(transaction)
    _apply_fields(transaction, transaction.account, data)
    record_correction(db, transaction, "Updated", before)
    db.commit()
    db.refresh(transaction)
    return transaction


def delete_transaction(db: Session, transaction: Transaction) -> None:
    before = transaction_snapshot(transaction)
    transaction.deleted_at = utc_now()
    record_correction(db, transaction, "Deleted", before)
    db.commit()


def list_corrections(db: Session, account_id: int) -> list[TransactionCorrection]:
    return list(db.scalars(select(TransactionCorrection).where(
        TransactionCorrection.account_id == account_id
    ).order_by(TransactionCorrection.changed_at.desc(), TransactionCorrection.id.desc())))


def _snapshot_from_json(data: dict) -> TransactionSnapshot:
    return TransactionSnapshot(
        date=data["date"], transaction_type=data["transaction_type"],
        amount=cents_to_dollars(data["amount_cents"]), description=data["description"],
        category=data.get("category"), classification=data.get("classification"),
        merchant=data.get("merchant"), location=data.get("location"),
        subcategory=data.get("subcategory"),
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
        merchant=transaction.merchant, location=transaction.location, category=transaction.category,
        subcategory=transaction.subcategory, created_at=transaction.created_at,
        updated_at=transaction.updated_at,
    )