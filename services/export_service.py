"""Build complete, lossless exports without changing financial values."""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.account import Account
from models.bill import Bill
from models.business import Business
from models.debt import Debt
from models.dependent import Dependent
from models.investment import Investment
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from utils.money import cents_to_dollars, milli_to_percent, units_to_quantity

EXPORT_FORMAT_VERSION = 1


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _money(cents: int) -> str:
    return str(cents_to_dollars(cents))


def _active(record) -> bool:
    """Treat pre-A2 model instances as active while migrations are pending."""
    return getattr(record, "active", True)


def get_schema_version(db: Session) -> str | None:
    try:
        return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        db.rollback()
        return None


def _all(db: Session, model) -> list:
    return list(db.scalars(select(model).order_by(model.id)))


def build_export(db: Session) -> dict:
    """Return every row, including inactive and soft-deleted history."""
    accounts = _all(db, Account)
    return {
        "format": "serenity-backup",
        "format_version": EXPORT_FORMAT_VERSION,
        "schema_version": get_schema_version(db),
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "accounts": [
            {
                "id": a.id, "name": a.name, "account_type": a.account_type,
                "classification": a.classification,
                "opening_balance_cents": a.opening_balance_cents,
                "opening_balance": _money(a.opening_balance_cents),
                "institution": a.institution, "notes": a.notes,
                "active": _active(a), "created_at": _iso(a.created_at),
                "updated_at": _iso(a.updated_at),
            }
            for a in accounts
        ],
        "businesses": [
            {
                "id": b.id,
                "name": b.name,
                "notes": b.notes,
                "active": _active(b),
                "created_at": _iso(b.created_at),
                "updated_at": _iso(b.updated_at),
            }
            for b in _all(db, Business)
        ],
        "dependents": [
            {
                "id": d.id,
                "display_name": d.display_name,
                "notes": d.notes,
                "active": _active(d),
                "created_at": _iso(d.created_at),
                "updated_at": _iso(d.updated_at),
            }
            for d in _all(db, Dependent)
        ],
        "transactions": [
            {
                "id": t.id, "account_id": t.account_id, "date": _iso(t.date),
                "transaction_type": t.transaction_type,
                "classification": t.classification,
                "amount_cents": t.amount_cents, "amount": _money(t.amount_cents),
                "description": t.description, "merchant": t.merchant,
                "location": t.location, "category": t.category,
                "subcategory": t.subcategory, "created_at": _iso(t.created_at),
                "updated_at": _iso(t.updated_at),
                "deleted_at": _iso(t.deleted_at),
                 "business_id": getattr(t, "business_id", None),
                 "dependent_id": getattr(t, "dependent_id", None),
            }
            for t in _all(db, Transaction)
        ],
        "transaction_corrections": [
            {
                "id": c.id, "account_id": c.account_id,
                "transaction_id": c.transaction_id, "action": c.action,
                "changed_at": _iso(c.changed_at), "before": c.before,
                "after": c.after,
            }
            for c in _all(db, TransactionCorrection)
        ],
        "bills": [
            {
                "id": b.id, "name": b.name, "amount_cents": b.amount_cents,
                "amount": _money(b.amount_cents), "due_date": _iso(b.due_date),
                "frequency": b.frequency, "category": b.category,
                "notes": b.notes, "active": _active(b),
                "created_at": _iso(b.created_at), "updated_at": _iso(b.updated_at),
            }
            for b in _all(db, Bill)
        ],
        "debts": [
            {
                "id": d.id, "name": d.name, "debt_type": d.debt_type,
                "balance_cents": d.balance_cents,
                "balance": _money(d.balance_cents),
                "interest_rate_milli": d.interest_rate_milli,
                "interest_rate": str(milli_to_percent(d.interest_rate_milli)),
                "minimum_payment_cents": d.minimum_payment_cents,
                "minimum_payment": _money(d.minimum_payment_cents),
                "due_date": _iso(d.due_date), "notes": d.notes,
                "active": _active(d), "created_at": _iso(d.created_at),
                "updated_at": _iso(d.updated_at),
            }
            for d in _all(db, Debt)
        ],
        "investments": [
            {
                "id": i.id, "name": i.name, "ticker": i.ticker,
                "quantity_units": i.quantity_units,
                "quantity": str(units_to_quantity(i.quantity_units)),
                "cost_basis_cents": i.cost_basis_cents,
                "cost_basis": _money(i.cost_basis_cents),
                "current_value_cents": i.current_value_cents,
                "current_value": _money(i.current_value_cents),
                "notes": i.notes, "active": _active(i),
                "created_at": _iso(i.created_at), "updated_at": _iso(i.updated_at),
            }
            for i in _all(db, Investment)
        ],
    }


TRANSACTION_CSV_COLUMNS = [
    "id", "date", "account", "transaction_type", "classification", "amount",
    "description", "merchant", "location", "category", "subcategory",
    "business", "dependent", "deleted", "created_at", "updated_at",
]


def _csv_cell(value) -> str:
    """Prevent spreadsheet formula execution while preserving visible text."""
    text_value = "" if value is None else str(value)
    if text_value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + text_value
    return text_value


def build_transactions_csv(db: Session) -> str:
    account_names = {a.id: a.name for a in _all(db, Account)}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TRANSACTION_CSV_COLUMNS)
    for t in _all(db, Transaction):
        writer.writerow([
            t.id, _iso(t.date), _csv_cell(account_names.get(t.account_id, "")),
            _csv_cell(t.transaction_type), _csv_cell(t.classification),
            _csv_cell(_money(t.amount_cents)), _csv_cell(t.description),
            _csv_cell(t.merchant), _csv_cell(t.location), _csv_cell(t.category),
            _csv_cell(t.subcategory),
            _csv_cell(
                t.business.name if getattr(t, "business", None) else ""
            ),
            _csv_cell(
                t.dependent.display_name if getattr(t, "dependent", None) else ""
            ),
            _csv_cell("yes" if t.deleted_at is not None else "no"),
            _iso(t.created_at), _iso(t.updated_at),
        ])
    return output.getvalue()