"""Owner-scoped organizational metadata. Never posts cash or values holdings."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import Account, utc_now
from models.investment import Investment
from models.portfolio import InvestmentAccount, Portfolio
from schemas.portfolio import InvestmentAccountWrite, PortfolioWrite
from services.ownership import require_owner_id
from models.conversion import OpeningPosition, ValuationEligibility
from services.financial_write_lock import lock_owner_financial_writes


class ContainerNotFound(ValueError):
    pass


class ContainerConflict(ValueError):
    pass


class ImmutableAccountLink(ValueError):
    pass

def selected_valuation_records(
    db: Session, owner_id: str
) -> tuple[set[int], list[OpeningPosition]]:
    """Return source IDs replaced by openings and active replacement openings.

    A missing eligibility row deliberately leaves an investment on its legacy
    path. Only the active/opening selection suppresses that source value;
    reversed links restore the legacy representation.
    """
    owner_id = require_owner_id(owner_id)
    selected_links = list(db.execute(select(
        ValuationEligibility.source_investment_id,
        ValuationEligibility.opening_position_id,
    ).where(
        ValuationEligibility.owner_id == owner_id,
        ValuationEligibility.representation == "opening",
        ValuationEligibility.status == "active",
    )))
    replaced_source_ids = {source_id for source_id, _ in selected_links}
    selected_opening_ids = {opening_id for _, opening_id in selected_links}
    openings = list(db.scalars(
        select(OpeningPosition)
        .join(Investment, (
            (Investment.owner_id == OpeningPosition.owner_id)
            & (Investment.id == OpeningPosition.source_investment_id)
        ))
        .where(
            OpeningPosition.owner_id == owner_id,
            OpeningPosition.id.in_(selected_opening_ids),
            OpeningPosition.status == "active",
            Investment.active.is_(True),
        )
        .order_by(OpeningPosition.id)
    ))
    return replaced_source_ids, openings
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
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    row = Portfolio(owner_id=owner_id, **data.model_dump())
    db.add(row)
    _commit(db, message="Could not create portfolio")
    db.refresh(row)
    return row


def update_portfolio(db: Session, owner_id: str, portfolio_id: int, data: PortfolioWrite) -> Portfolio:
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    row = get_portfolio(db, owner_id, portfolio_id, lock=True)
    row.name, row.notes = data.name, data.notes
    _commit(db, message="Could not update portfolio")
    db.refresh(row)
    return row


def set_portfolio_active(db: Session, owner_id: str, portfolio_id: int, active: bool) -> Portfolio:
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
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
    ).execution_options(populate_existing=True))
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
    lock_owner_financial_writes(db, owner_id)
    _require_active_parents(db, owner_id, data.portfolio_id, data.account_id)
    row = InvestmentAccount(owner_id=owner_id, **data.model_dump())
    db.add(row)
    _commit(db, message="This account is already linked to an investment account")
    db.refresh(row)
    return row


def update_investment_account(
    db: Session, owner_id: str, container_id: int, data: InvestmentAccountWrite
) -> InvestmentAccount:
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
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
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    row = get_investment_account(db, owner_id, container_id, lock=True)
    if active:
        _require_active_parents(db, owner_id, row.portfolio_id, row.account_id)
    row.active = active
    row.updated_at = utc_now()
    _commit(db, message="Could not change investment account status")
    db.refresh(row)
    return row

def eligible_legacy_investments(
    db: Session, owner_id: str, investments: list[Investment] | None = None
) -> list[Investment]:
    """Active legacy valuations not superseded by a selected opening."""
    owner_id = require_owner_id(owner_id)
    if investments is None:
        investments = list(db.scalars(select(Investment).where(
            Investment.owner_id == owner_id
        )))
    replaced_source_ids, _ = selected_valuation_records(db, owner_id)
    eligible = []
    for investment in investments:
        if investment.owner_id != owner_id:
            continue
        if investment.active is None:
            raise ValueError(f"{type(investment).__name__} has no active lifecycle state")
        if investment.active and not investment.review_pending and investment.id not in replaced_source_ids:
            eligible.append(investment)
    return eligible
