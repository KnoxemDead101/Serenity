"""Build complete, lossless exports without changing financial values."""

import csv
import io
from datetime import datetime, timezone

from sqlalchemy import inspect, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from models.account import Account
from models.bill import Bill
from models.business import Business
from models.debt import Debt
from models.dependent import Dependent
from models.income_profile import IncomeProfile
from models.investment import Investment
from models.instrument import Instrument, InstrumentSpecification
from models.portfolio import InvestmentAccount, Portfolio
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from models.conversion import (
    CashReconciliationEntry,
    ConversionEvent,
    OpeningPosition,
    ReconciliationApproval,
    ValuationEligibility,
)
from models.goal import Goal
from models.goal_composition import GoalCheckpoint, GoalItem, GoalMilestone
from services.goal_composition_service import to_checkpoint_read, to_item_read, to_milestone_read
from services.goal_service import to_goal_read
from services.ownership import require_owner_id
from utils.money import cents_to_dollars, milli_to_percent, units_to_quantity

from services import account_service
from services import portfolio_service
from services.financial_write_lock import lock_owner_financial_writes

EXPORT_FORMAT_VERSION = 7


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _money(cents: int) -> str:
    return str(cents_to_dollars(cents))


def _active(record) -> bool:
    """Treat pre-A2 model instances as active while migrations are pending."""
    return getattr(record, "active", True)


def get_schema_version(db: Session) -> str | None:
    try:
        with db.begin_nested():
            if not inspect(db.connection()).has_table("alembic_version"):
                return None
            return db.execute(text("SELECT version_num FROM alembic_version")).scalar()
    except SQLAlchemyError:
        return None


def _all(db: Session, model, owner_id: str) -> list:
    owner_id = require_owner_id(owner_id)
    return list(db.scalars(select(model).where(
        model.owner_id == owner_id
    ).order_by(model.id).execution_options(populate_existing=True)))

def _ledger_record(record) -> dict:
    """Serialize a conversion ledger row without losing integer/binary evidence."""
    result = {}
    for column in record.__table__.columns:
        value = getattr(record, column.name)
        if isinstance(value, bytes):
            value = value.hex()
        elif hasattr(value, "isoformat"):
            value = value.isoformat()
        result[column.name] = value
    return result


def _export_goals(db: Session, owner_id: str) -> list[dict]:
    """Batch composition once per family, rather than once per parent Goal."""
    goals = _all(db, Goal, owner_id)
    grouped = {}
    for model in (GoalItem, GoalMilestone, GoalCheckpoint):
        by_goal = {}
        rows = db.scalars(select(model).join(
            Goal, (model.goal_id == Goal.id) & (model.owner_id == Goal.owner_id),
        ).where(Goal.owner_id == owner_id).order_by(model.sort_order, model.id))
        for row in rows:
            by_goal.setdefault(row.goal_id, []).append(row)
        grouped[model] = by_goal
    exported = []
    for goal in goals:
        data = to_goal_read(goal).model_dump(mode="json")
        data["items"] = [
            to_item_read(row).model_dump(mode="json")
            for row in grouped[GoalItem].get(goal.id, [])
        ]
        data["milestones"] = [
            to_milestone_read(row).model_dump(mode="json")
            for row in grouped[GoalMilestone].get(goal.id, [])
        ]
        # Reached is a display-time comparison, not backup state to restore.
        data["checkpoints"] = [
            to_checkpoint_read(row, goal).model_dump(mode="json", exclude={"reached"})
            for row in grouped[GoalCheckpoint].get(goal.id, [])
        ]
        exported.append(data)
    return exported


def build_export(db: Session, owner_id: str) -> dict:
    """Return every row, including inactive and soft-deleted history."""
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    accounts = _all(db, Account, owner_id)
    current_account_balances = {
        account.id: account_service.calculate_current_balance_cents(account, db)
        for account in accounts
    }
    replaced_source_ids, selected_openings = portfolio_service.selected_valuation_records(db, owner_id)
    selected_opening_ids = {position.id for position in selected_openings}
    eligibility_by_source = {
        row.source_investment_id: row
        for row in _all(db, ValuationEligibility, owner_id)
    }
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
                "current_balance_cents": current_account_balances[a.id],
                "current_balance": _money(current_account_balances[a.id]),
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
            for b in _all(db, Business, owner_id)
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
            for d in _all(db, Dependent, owner_id)
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
            for t in _all(db, Transaction, owner_id)
        ],
        "transaction_corrections": [
            {
                "id": c.id, "account_id": c.account_id,
                "transaction_id": c.transaction_id, "action": c.action,
                "changed_at": _iso(c.changed_at), "before": c.before,
                "after": c.after,
            }
            for c in _all(db, TransactionCorrection, owner_id)
        ],
        "bills": [
            {
                "id": b.id, "name": b.name, "amount_cents": b.amount_cents,
                "amount": _money(b.amount_cents), "due_date": _iso(b.due_date),
                "frequency": b.frequency, "category": b.category,
                "notes": b.notes, "active": _active(b),
                "created_at": _iso(b.created_at), "updated_at": _iso(b.updated_at),
            }
            for b in _all(db, Bill, owner_id)
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
            for d in _all(db, Debt, owner_id)
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
                "selected_for_valuation": (
                    _active(i) and not i.review_pending
                    and i.id not in replaced_source_ids
                ),
                "valuation_representation": (
                    eligibility_by_source[i.id].representation
                    if i.id in eligibility_by_source else "legacy"
                ),
                "notes": i.notes, "active": _active(i),
                "investment_account_id": i.investment_account_id,
                "portfolio_id": i.portfolio_id,
                "review_pending": i.review_pending,
                "created_at": _iso(i.created_at), "updated_at": _iso(i.updated_at),
            }
            for i in _all(db, Investment, owner_id)
        ],
        "reconciliation_approvals": [
            _ledger_record(row) for row in _all(db, ReconciliationApproval, owner_id)
        ],
        "opening_positions": [
            {
                **_ledger_record(row),
                "selected_for_valuation": row.id in selected_opening_ids,
            }
            for row in _all(db, OpeningPosition, owner_id)
        ],
        "valuation_eligibility": [
            _ledger_record(row) for row in _all(db, ValuationEligibility, owner_id)
        ],
        "cash_reconciliation_entries": [
            _ledger_record(row) for row in _all(db, CashReconciliationEntry, owner_id)
        ],
        "conversion_events": [
            _ledger_record(row) for row in _all(db, ConversionEvent, owner_id)
        ],
        "portfolios": [
            {
                "id": p.id, "name": p.name, "notes": p.notes,
                "active": p.active, "created_at": _iso(p.created_at),
                "updated_at": _iso(p.updated_at),
            }
            for p in _all(db, Portfolio, owner_id)
        ],
        "investment_accounts": [
            {
                "id": container.id,
                "portfolio_id": container.portfolio_id,
                "account_id": container.account_id,
                "name": container.name, "notes": container.notes,
                "active": container.active,
                "created_at": _iso(container.created_at),
                "updated_at": _iso(container.updated_at),
            }
            for container in _all(db, InvestmentAccount, owner_id)
        ],
        # Reference metadata is separate from Investments (actual starting
        # positions). Include every version so future historical calculations
        # remain reproducible; values are integer units, not JSON floats.
        "instruments": [
            {
                "id": i.id,
                "symbol": i.symbol,
                "active": i.active,
                "created_at": _iso(i.created_at),
                "updated_at": _iso(i.updated_at),
            }
            for i in _all(db, Instrument, owner_id)
        ],
        "instrument_specifications": [
            {
                "id": spec.id,
                "instrument_id": spec.instrument_id,
                "version": spec.version,
                "symbol": spec.symbol,
                "name": spec.name,
                "asset_type": spec.asset_type,
                "exchange": spec.exchange,
                "currency": spec.currency,
                "tick_size_units": spec.tick_size_units,
                "point_value_units": spec.point_value_units,
                "created_at": _iso(spec.created_at),
            }
            for spec in db.scalars(
                select(InstrumentSpecification).join(Instrument).where(
                    InstrumentSpecification.owner_id == owner_id,
                    Instrument.owner_id == owner_id,
                ).order_by(InstrumentSpecification.id)
            )
        ],
        "income_profiles": [
            {
                "id": p.id,
                "name": p.name,
                "income_type": p.income_type,
                "classification": p.classification,
                "pay_frequency": p.pay_frequency,
                "hourly_rate_cents": p.hourly_rate_cents,
                "standard_hours_hundredths": p.standard_hours_hundredths,
                "expected_hours_hundredths": p.expected_hours_hundredths,
                "annual_salary_cents": p.annual_salary_cents,
                "amount_per_period_cents": p.amount_per_period_cents,
                "expected_net_per_period_cents": p.expected_net_per_period_cents,
                "notes": p.notes,
                "active": p.active,
                "created_at": _iso(p.created_at),
                "updated_at": _iso(p.updated_at),
            }
            for p in _all(db, IncomeProfile, owner_id)
        ],
        # Append owner-scoped goals, including archived records. Read models
        # supply raw cents, decimal strings, ISO dates and UTC timestamps.
        # Composition arrays are additive fields: existing keys/values retain
        # their meaning; this combined format is version 7.
        "goals": _export_goals(db, owner_id),
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


def build_transactions_csv(
    db: Session, owner_id: str
) -> str:
    account_names = {a.id: a.name for a in _all(db, Account, owner_id)}
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(TRANSACTION_CSV_COLUMNS)
    for t in _all(db, Transaction, owner_id):
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
