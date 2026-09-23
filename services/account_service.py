"""Business logic for accounts and account-level balance totals."""

from collections import defaultdict

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.account import Account
from schemas.account import AccountCreate, AccountRead, AccountTotals
from services import transaction_service
from utils.choices import ACCOUNT_CLASSIFICATIONS
from utils.money import cents_to_dollars, dollars_to_cents


def create_account(db: Session, data: AccountCreate) -> Account:
    account = Account(
        name=data.name, account_type=data.account_type, classification=data.classification,
        opening_balance_cents=dollars_to_cents(data.opening_balance),
        institution=data.institution, notes=data.notes,
    )
    db.add(account)
    db.commit()
    db.refresh(account)
    return account


def list_accounts(db: Session) -> list[Account]:
    return list(db.scalars(select(Account).order_by(Account.name)))


def get_account(db: Session, account_id: int) -> Account | None:
    return db.get(Account, account_id)


def calculate_current_balance_cents(account: Account) -> int:
    return account.opening_balance_cents + transaction_service.active_balance_change_cents(account)


def to_account_read(account: Account) -> AccountRead:
    return AccountRead(
        id=account.id, name=account.name, account_type=account.account_type,
        classification=account.classification,
        opening_balance=cents_to_dollars(account.opening_balance_cents),
        current_balance=cents_to_dollars(calculate_current_balance_cents(account)),
        institution=account.institution, notes=account.notes, active=account.active,
        created_at=account.created_at, updated_at=account.updated_at,
    )


def get_account_totals(db: Session) -> AccountTotals:
    accounts = list_accounts(db)
    by_classification: dict[str, int] = defaultdict(int)
    for classification in ACCOUNT_CLASSIFICATIONS:
        by_classification[classification] = 0
    total = 0
    for account in accounts:
        balance = calculate_current_balance_cents(account)
        total += balance
        by_classification[account.classification] += balance
    return AccountTotals(
        account_count=len(accounts), total_balance=cents_to_dollars(total),
        balance_by_classification={k: cents_to_dollars(v) for k, v in by_classification.items()},
    )