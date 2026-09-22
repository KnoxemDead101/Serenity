"""
Account service: the business logic for accounts.

Services sit between the API routes and the database:

    api/accounts.py  ->  services/account_service.py  ->  database

Routes deal with HTTP (URLs, status codes). This file deals with the
actual rules: how an account is created and how balances are calculated.
Because it knows nothing about HTTP, the same functions could later be
reused by a command-line tool, a scheduled job, or Brainiac.
"""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.account import Account
from schemas.account import AccountCreate, AccountRead, AccountTotals
from utils.choices import ACCOUNT_CLASSIFICATIONS
from utils.money import cents_to_dollars, dollars_to_cents


def create_account(db: Session, data: AccountCreate) -> Account:
    """Save a new account. `data` has already been validated by the schema."""
    account = Account(
        name=data.name,
        account_type=data.account_type,
        classification=data.classification,
        opening_balance_cents=dollars_to_cents(data.opening_balance),
        institution=data.institution,
        notes=data.notes,
    )
    db.add(account)
    db.commit()  # actually writes to the database
    db.refresh(account)  # reloads it so `account.id` is filled in
    return account


def list_accounts(db: Session) -> list[Account]:
    """All accounts, alphabetical by name."""
    return list(db.scalars(select(Account).order_by(Account.name)))


def get_account(db: Session, account_id: int) -> Account | None:
    """One account by id, or None if it doesn't exist."""
    return db.get(Account, account_id)


def calculate_current_balance_cents(account: Account) -> int:
    """
    The account's balance right now, in cents.

    For now this is just the opening balance. When transactions are added
    (next slice), this becomes:
        opening balance + income transactions - expense transactions
    Keeping the formula in this one function means only this spot changes.
    """
    return account.opening_balance_cents


def to_account_read(account: Account) -> AccountRead:
    """Convert a database Account (cents) into the API shape (dollars)."""
    return AccountRead(
        id=account.id,
        name=account.name,
        account_type=account.account_type,
        classification=account.classification,
        opening_balance=cents_to_dollars(account.opening_balance_cents),
        current_balance=cents_to_dollars(calculate_current_balance_cents(account)),
        institution=account.institution,
        notes=account.notes,
        created_at=account.created_at,
        updated_at=account.updated_at,
    )


def get_account_totals(db: Session) -> AccountTotals:
    """
    Add up balances across all accounts, overall and by classification.

    Note: until Debt is modeled (Milestone 2), a credit card is just an
    account. Enter what you owe as a NEGATIVE opening balance so it
    reduces the total instead of increasing it.
    """
    accounts = list_accounts(db)

    # Start every classification at 0 so the dashboard always shows all four.
    cents_by_classification: dict[str, int] = defaultdict(int)
    for classification in ACCOUNT_CLASSIFICATIONS:
        cents_by_classification[classification] = 0

    total_cents = 0
    for account in accounts:
        balance = calculate_current_balance_cents(account)
        total_cents += balance
        cents_by_classification[account.classification] += balance

    return AccountTotals(
        account_count=len(accounts),
        total_balance=cents_to_dollars(total_cents),
        balance_by_classification={
            name: cents_to_dollars(cents) for name, cents in cents_by_classification.items()
        },
    )
