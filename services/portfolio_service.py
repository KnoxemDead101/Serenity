"""Owner-scoped organizational metadata. Never posts cash or values holdings."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import Account, utc_now
from models.investment import Investment
from models.portfolio import InvestmentAccount, Portfolio
from schemas.portfolio import InvestmentAccountWrite, PortfolioWrite
from services.ownership import require_owner_id


class ContainerNotFound(ValueError):
    pass


class ContainerConflict(ValueError):
    pass


class ImmutableAccountLink(ValueError):
    pass


def _commit(db: Session, *, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise ContainerConflict(message) from exc


def list_portfolios(db: Session, owner_id: str) -> list[Portfolio]:
    return list(db.scalars(select(Portfolio).where(
        Portfolio.owner_id == require_owner_id(owner_id)
    ).order_by(Portfolio.id)))


def get_portfolio(db: Session, owner_id: str, portfolio_id: int, *, lock: bool = False) -> Portfolio:
    statement = select(Portfolio).where(
        Portfolio.owner_id == require_owner_id(owner_id), Portfolio.id == portfolio_id
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(statement)
    if row is None:
        raise ContainerNotFound("Portfolio not found")
    return row


def create_portfolio(db: Session, owner_id: str, data: PortfolioWrite) -> Portfolio:
    row = Portfolio(owner_id=require_owner_id(owner_id), **data.model_dump())
    db.add(row)
    _commit(db, message="Could not create portfolio")
    db.refresh(row)
    return row


def update_portfolio(db: Session, owner_id: str, portfolio_id: int, data: PortfolioWrite) -> Portfolio:
    row = get_portfolio(db, owner_id, portfolio_id)
    row.name, row.notes = data.name, data.notes
    _commit(db, message="Could not update portfolio")
    db.refresh(row)
    return row


def set_portfolio_active(db: Session, owner_id: str, portfolio_id: int, active: bool) -> Portfolio:
    # Serialize the child check with every create/move/reactivation that can
    # add an active child (on PostgreSQL). SQLite serializes writers itself.
    row = get_portfolio(db, owner_id, portfolio_id, lock=True)
    if not active and db.scalar(select(InvestmentAccount.id).where(
        InvestmentAccount.owner_id == row.owner_id,
        InvestmentAccount.portfolio_id == row.id,
        InvestmentAccount.active.is_(True),
    ).limit(1)) is not None:
        raise ContainerConflict("Deactivate active investment accounts before deactivating this portfolio")
    if not active and db.scalar(select(Investment.id).where(
        Investment.owner_id == row.owner_id, Investment.portfolio_id == row.id,
        Investment.active.is_(True),
    ).limit(1)) is not None:
        raise ContainerConflict("Deactivate or move active investments before deactivating this portfolio")
    row.active = active
    row.updated_at = utc_now()
    _commit(db, message="Could not change portfolio status")
    db.refresh(row)
    return row


def list_investment_accounts(db: Session, owner_id: str) -> list[InvestmentAccount]:
    return list(db.scalars(select(InvestmentAccount).where(
        InvestmentAccount.owner_id == require_owner_id(owner_id)
    ).order_by(InvestmentAccount.id)))


def get_investment_account(
    db: Session, owner_id: str, container_id: int, *, lock: bool = False
) -> InvestmentAccount:
    statement = select(InvestmentAccount).where(
        InvestmentAccount.owner_id == require_owner_id(owner_id),
        InvestmentAccount.id == container_id,
    )
    if lock:
        # A different transaction may have moved the row since it entered
        # this session's identity map. Reload *after* acquiring the row lock.
        statement = statement.with_for_update().execution_options(populate_existing=True)
    row = db.scalar(statement)
    if row is None:
        raise ContainerNotFound("Investment account not found")
    return row


def _require_account(db: Session, owner_id: str, account_id: int) -> Account:
    account = db.scalar(select(Account).where(
        Account.owner_id == require_owner_id(owner_id), Account.id == account_id
    ))
    if account is None:
        raise ContainerNotFound("Account not found")
    return account


def _require_active_parents(db: Session, owner_id: str, portfolio_id: int, account_id: int) -> None:
    portfolio = get_portfolio(db, owner_id, portfolio_id, lock=True)
    account = _require_account(db, owner_id, account_id)
    if not portfolio.active:
        raise ContainerConflict("Portfolio is inactive")
    if not account.active:
        raise ContainerConflict("Account is inactive")


def create_investment_account(db: Session, owner_id: str, data: InvestmentAccountWrite) -> InvestmentAccount:
    owner_id = require_owner_id(owner_id)
    _require_active_parents(db, owner_id, data.portfolio_id, data.account_id)
    row = InvestmentAccount(owner_id=owner_id, **data.model_dump())
    db.add(row)
    _commit(db, message="This account is already linked to an investment account")
    db.refresh(row)
    return row


def update_investment_account(
    db: Session, owner_id: str, container_id: int, data: InvestmentAccountWrite
) -> InvestmentAccount:
    row = get_investment_account(db, owner_id, container_id, lock=True)
    # Never disclose whether an arbitrary foreign ID exists.
    _require_account(db, owner_id, data.account_id)
    if row.account_id != data.account_id:
        raise ImmutableAccountLink("An investment account's cash account cannot be changed")
    if row.portfolio_id != data.portfolio_id:
        _require_active_parents(db, owner_id, data.portfolio_id, data.account_id)
    row.name, row.notes, row.portfolio_id = data.name, data.notes, data.portfolio_id
    _commit(db, message="Could not update investment account")
    db.refresh(row)
    return row


def set_investment_account_active(
    db: Session, owner_id: str, container_id: int, active: bool
) -> InvestmentAccount:
    row = get_investment_account(db, owner_id, container_id, lock=True)
    if active:
        _require_active_parents(db, owner_id, row.portfolio_id, row.account_id)
    row.active = active
    row.updated_at = utc_now()
    _commit(db, message="Could not change investment account status")
    db.refresh(row)
    return row