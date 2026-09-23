from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from models.bill import Bill
from models.debt import Debt
from models.investment import Investment
from schemas.finance import (
    BillCreate,
    BillRead,
    BillUpdate,
    DebtCreate,
    DebtRead,
    DebtUpdate,
    FinanceSummary,
    InvestmentCreate,
    InvestmentRead,
    InvestmentUpdate,
)
from services import finance_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api", tags=["Finance"])


def _require_bill(db: Session, bill_id: int, owner_id: str) -> Bill:
    bill = finance_service.get_bill(db, bill_id, owner_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


def _require_debt(db: Session, debt_id: int, owner_id: str) -> Debt:
    debt = finance_service.get_debt(db, debt_id, owner_id)
    if debt is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    return debt


def _require_investment(db: Session, investment_id: int, owner_id: str) -> Investment:
    investment = finance_service.get_investment(db, investment_id, owner_id)
    if investment is None:
        raise HTTPException(status_code=404, detail="Investment not found")
    return investment


@router.get("/finance/options")
def get_finance_options():
    return finance_service.get_finance_options()


@router.post("/bills", response_model=BillRead, status_code=status.HTTP_201_CREATED)
def create_bill(
    data: BillCreate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_bill_read(finance_service.create_bill(db, data, user_id))


@router.get("/bills", response_model=list[BillRead])
def list_bills(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return [
        finance_service.to_bill_read(bill)
        for bill in finance_service.list_bills(db, user_id)
    ]


@router.get("/bills/{bill_id}", response_model=BillRead)
def get_bill(
    bill_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_bill_read(_require_bill(db, bill_id, user_id))


@router.put("/bills/{bill_id}", response_model=BillRead)
def update_bill(
    bill_id: int,
    data: BillUpdate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_bill_read(
        finance_service.update_bill(db, _require_bill(db, bill_id, user_id), data)
    )


@router.post("/bills/{bill_id}/deactivate", response_model=BillRead)
def deactivate_bill(
    bill_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_bill_read(
        finance_service.set_bill_active(db, _require_bill(db, bill_id, user_id), False)
    )


@router.post("/bills/{bill_id}/reactivate", response_model=BillRead)
def reactivate_bill(
    bill_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_bill_read(
        finance_service.set_bill_active(db, _require_bill(db, bill_id, user_id), True)
    )


@router.post("/debts", response_model=DebtRead, status_code=status.HTTP_201_CREATED)
def create_debt(
    data: DebtCreate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_debt_read(finance_service.create_debt(db, data, user_id))


@router.get("/debts", response_model=list[DebtRead])
def list_debts(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return [
        finance_service.to_debt_read(debt)
        for debt in finance_service.list_debts(db, user_id)
    ]


@router.get("/debts/{debt_id}", response_model=DebtRead)
def get_debt(
    debt_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_debt_read(_require_debt(db, debt_id, user_id))


@router.put("/debts/{debt_id}", response_model=DebtRead)
def update_debt(
    debt_id: int,
    data: DebtUpdate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_debt_read(
        finance_service.update_debt(db, _require_debt(db, debt_id, user_id), data)
    )


@router.post("/debts/{debt_id}/deactivate", response_model=DebtRead)
def deactivate_debt(
    debt_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_debt_read(
        finance_service.set_debt_active(db, _require_debt(db, debt_id, user_id), False)
    )


@router.post("/debts/{debt_id}/reactivate", response_model=DebtRead)
def reactivate_debt(
    debt_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_debt_read(
        finance_service.set_debt_active(db, _require_debt(db, debt_id, user_id), True)
    )


@router.post("/investments", response_model=InvestmentRead, status_code=status.HTTP_201_CREATED)
def create_investment(
    data: InvestmentCreate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_investment_read(
        finance_service.create_investment(db, data, user_id)
    )


@router.get("/investments", response_model=list[InvestmentRead])
def list_investments(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return [
        finance_service.to_investment_read(investment)
        for investment in finance_service.list_investments(db, user_id)
    ]


@router.get("/investments/{investment_id}", response_model=InvestmentRead)
def get_investment(
    investment_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_investment_read(
        _require_investment(db, investment_id, user_id)
    )


@router.put("/investments/{investment_id}", response_model=InvestmentRead)
def update_investment(
    investment_id: int,
    data: InvestmentUpdate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_investment_read(
        finance_service.update_investment(
            db, _require_investment(db, investment_id, user_id), data
        )
    )


@router.post("/investments/{investment_id}/deactivate", response_model=InvestmentRead)
def deactivate_investment(
    investment_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_investment_read(
        finance_service.set_investment_active(
            db, _require_investment(db, investment_id, user_id), False
        )
    )


@router.post("/investments/{investment_id}/reactivate", response_model=InvestmentRead)
def reactivate_investment(
    investment_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return finance_service.to_investment_read(
        finance_service.set_investment_active(
            db, _require_investment(db, investment_id, user_id), True
        )
    )


@router.get("/finance/summary", response_model=FinanceSummary)
def get_finance_summary(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return finance_service.get_finance_summary(db, user_id)