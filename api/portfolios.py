"""Private organization of existing cash ledgers; no holding or valuation APIs."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from schemas.portfolio import (
    InvestmentAccountRead, InvestmentAccountWrite, PortfolioRead, PortfolioWrite,
)
from services import portfolio_service as service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api", tags=["Portfolios"])


def _call(operation, *args):
    try:
        return operation(*args)
    except service.ContainerNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.ContainerConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.ImmutableAccountLink as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/portfolios", response_model=list[PortfolioRead])
def list_portfolios(owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return service.list_portfolios(db, owner_id)


@router.post("/portfolios", response_model=PortfolioRead, status_code=status.HTTP_201_CREATED)
def create_portfolio(data: PortfolioWrite, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.create_portfolio, db, owner_id, data)


@router.get("/portfolios/{portfolio_id}", response_model=PortfolioRead)
def get_portfolio(portfolio_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.get_portfolio, db, owner_id, portfolio_id)


@router.put("/portfolios/{portfolio_id}", response_model=PortfolioRead)
def update_portfolio(portfolio_id: int, data: PortfolioWrite, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.update_portfolio, db, owner_id, portfolio_id, data)


@router.post("/portfolios/{portfolio_id}/deactivate", response_model=PortfolioRead)
def deactivate_portfolio(portfolio_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.set_portfolio_active, db, owner_id, portfolio_id, False)


@router.post("/portfolios/{portfolio_id}/reactivate", response_model=PortfolioRead)
def reactivate_portfolio(portfolio_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.set_portfolio_active, db, owner_id, portfolio_id, True)


@router.get("/investment-accounts", response_model=list[InvestmentAccountRead])
def list_investment_accounts(owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return service.list_investment_accounts(db, owner_id)


@router.post("/investment-accounts", response_model=InvestmentAccountRead, status_code=status.HTTP_201_CREATED)
def create_investment_account(data: InvestmentAccountWrite, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.create_investment_account, db, owner_id, data)


@router.get("/investment-accounts/{container_id}", response_model=InvestmentAccountRead)
def get_investment_account(container_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.get_investment_account, db, owner_id, container_id)


@router.put("/investment-accounts/{container_id}", response_model=InvestmentAccountRead)
def update_investment_account(container_id: int, data: InvestmentAccountWrite, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.update_investment_account, db, owner_id, container_id, data)


@router.post("/investment-accounts/{container_id}/deactivate", response_model=InvestmentAccountRead)
def deactivate_investment_account(container_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.set_investment_account_active, db, owner_id, container_id, False)


@router.post("/investment-accounts/{container_id}/reactivate", response_model=InvestmentAccountRead)
def reactivate_investment_account(container_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return _call(service.set_investment_account_active, db, owner_id, container_id, True)