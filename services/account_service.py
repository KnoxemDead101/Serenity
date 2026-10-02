"""
Account service: the business logic for accounts.

Services sit between the API routes and the database:

    api/accounts.py  ->  services/account_service.py  ->  database

Routes deal with HTTP (URLs, status codes). This file deals with the
actual rules: how an account is created and how balances are calculated.
Because it knows nothing about HTTP, the same functions could later be
reused by a command-line tool, a scheduled job, or Brainiac.

Transaction rules live in services/transaction_service.py.
"""

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import func, select
from sqlalchemy.orm import Session, object_session
from sqlalchemy import inspect

from models.account import Account
from models.conversion import CashReconciliationEntry
from schemas.account import AccountCreate, AccountRead, AccountTotals, AccountUpdate
from services import transaction_service
from services.financial_write_lock import lock_owner_financial_writes
from services.ownership import require_owner_id
from utils.choices import ACCOUNT_CLASSIFICATIONS
from utils.money import cents_to_dollars, dollars_to_cents


def create_account(db: Session, data: AccountCreate, owner_id: str) -> Account:
    """Save a validated account using integer cents in storage."""
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    account = Account(
        owner_id=owner_id,
        name=data.name, account_type=data.account_type, classification=data.classification,
        opening_balance_cents=dollars_to_cents(data.opening_balance),
        institution=data.institution, notes=data.notes,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def update_account(db: Session, account: Account, data: AccountUpdate) -> Account:
    """Replace an account's editable fields with validated values."""
    lock_owner_financial_writes(db, account.owner_id)
    account = _reload_account_for_write(db, account)
    account.name = data.name
    account.account_type = data.account_type
    account.classification = data.classification
    account.opening_balance_cents = dollars_to_cents(data.opening_balance)
    account.institution = data.institution
    account.notes = data.notes
    db.commit()
    db.refresh(account)
    return account


def set_account_active(db: Session, account: Account, active: bool) -> Account:
    """Deactivate or reactivate without deleting the account or its history."""
    lock_owner_financial_writes(db, account.owner_id)
    account = _reload_account_for_write(db, account)
    account.active = active
    db.commit()
    db.refresh(account)
    return account


def _reload_account_for_write(db: Session, account: Account) -> Account:
    """Discard stale identity-map state after acquiring the owner lock."""
    refreshed = db.scalar(
        select(Account)
        .where(Account.id == account.id, Account.owner_id == account.owner_id)
        .execution_options(populate_existing=True)
    )
    if refreshed is None:
        raise ValueError("Account no longer exists for this owner")
    return refreshed


def list_accounts(db: Session, owner_id: str) -> list[Account]:
    """Return accounts alphabetically by name."""
    return list(db.scalars(
        select(Account).where(
            Account.owner_id == require_owner_id(owner_id)
        ).order_by(Account.name)
    ))


def get_account(db: Session, account_id: int, owner_id: str) -> Account | None:
    """Return one account by id, or None when it does not exist."""
    return db.scalar(select(Account).where(
        Account.id == account_id, Account.owner_id == require_owner_id(owner_id)
    ))


def calculate_current_balance_cents(account: Account, db: Session | None = None) -> int:
    """
    The account's balance right now, in cents:

        opening balance + income - expenses + non-income cash corrections

    The sign of each transaction is decided in transaction_service.
    """
    if db is None:
        db = object_session(account)
        if db is None and not inspect(account).transient:
            raise ValueError("Current account balance requires a database context")
    corrections = cash_reconciliation_cents(account, db)
    return (
        account.opening_balance_cents
        + transaction_service.active_balance_change_cents(account)
        + corrections
    )


def cash_reconciliation_cents(account: Account, db: Session | None = None) -> int:
    corrections = 0
    if db is not None:
        corrections = int(db.scalar(select(func.coalesce(func.sum(
            CashReconciliationEntry.delta_cents
        ), 0)).where(
            CashReconciliationEntry.owner_id == account.owner_id,
            CashReconciliationEntry.account_id == account.id,
        )) or 0)
    return corrections


def total_balance_cents(accounts: Iterable[Account], db: Session | None = None) -> int:
    """
    Sum of the current balances of the given accounts, in cents.

    Used by both the account totals below and the dashboard's net worth,
    so "total balance" has exactly one formula.
    """
    return sum(calculate_current_balance_cents(account, db) for account in accounts)


def to_account_read(account: Account, db: Session | None = None) -> AccountRead:
    db = db or object_session(account)
    corrections = cash_reconciliation_cents(account, db)
    return AccountRead(
        id=account.id, name=account.name, account_type=account.account_type,
        classification=account.classification,
        opening_balance=cents_to_dollars(account.opening_balance_cents),
        current_balance=cents_to_dollars(calculate_current_balance_cents(account, db)),
        cash_reconciliation_cents=corrections,
        cash_reconciliation=cents_to_dollars(corrections),
        institution=account.institution, notes=account.notes, active=account.active,
        created_at=account.created_at, updated_at=account.updated_at,
    )


def get_account_totals(db: Session, owner_id: str) -> AccountTotals:
    """
    Add up balances across all accounts, overall and by classification.

    Groups by the ACCOUNT's classification (where the money sits).
    Debts, including credit cards, are summarized separately and are not
    duplicated in account balances.
    """
    lock_owner_financial_writes(db, owner_id)
    accounts = list_accounts(db, owner_id)
    # Start every classification at 0 so the dashboard always shows all four.
    cents_by_classification: dict[str, int] = defaultdict(int)
    for classification in ACCOUNT_CLASSIFICATIONS:
        cents_by_classification[classification] = 0
    for account in accounts:
        cents_by_classification[account.classification] += calculate_current_balance_cents(account, db)
    return AccountTotals(
        account_count=len(accounts), total_balance=cents_to_dollars(total_balance_cents(accounts, db)),
        balance_by_classification={
            name: cents_to_dollars(cents) for name, cents in cents_by_classification.items()
        },
    )