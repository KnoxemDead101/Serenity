from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

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


def _require_bill(db: Session, bill_id: int) -> Bill:
    bill = finance_service.get_bill(db, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return bill


def _require_debt(db: Session, debt_id: int) -> Debt:
    debt = finance_service.get_debt(db, debt_id)
    if debt is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    return debt


def _require_investment(db: Session, investment_id: int) -> Investment:
    investment = finance_service.get_investment(db, investment_id)
    if investment is None:
        raise HTTPException(status_code=404, detail="Investment not found")
    return investment


@router.get("/finance/options")
def get_finance_options():
    return finance_service.get_finance_options()


@router.post("/bills", response_model=BillRead, status_code=status.HTTP_201_CREATED)
def create_bill(data: BillCreate, db: Session = Depends(get_db)):
    return finance_service.to_bill_read(finance_service.create_bill(db, data))


@router.get("/bills", response_model=list[BillRead])
def list_bills(db: Session = Depends(get_db)):
    return [finance_service.to_bill_read(bill) for bill in finance_service.list_bills(db)]


@router.get("/bills/{bill_id}", response_model=BillRead)
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    return finance_service.to_bill_read(_require_bill(db, bill_id))


@router.put("/bills/{bill_id}", response_model=BillRead)
def update_bill(bill_id: int, data: BillUpdate, db: Session = Depends(get_db)):
    return finance_service.to_bill_read(
        finance_service.update_bill(db, _require_bill(db, bill_id), data)
    )


@router.post("/bills/{bill_id}/deactivate", response_model=BillRead)
def deactivate_bill(bill_id: int, db: Session = Depends(get_db)):
    return finance_service.to_bill_read(
        finance_service.set_bill_active(db, _require_bill(db, bill_id), False)
    )


@router.post("/bills/{bill_id}/reactivate", response_model=BillRead)
def reactivate_bill(bill_id: int, db: Session = Depends(get_db)):
    return finance_service.to_bill_read(
        finance_service.set_bill_active(db, _require_bill(db, bill_id), True)
    )


@router.post("/debts", response_model=DebtRead, status_code=status.HTTP_201_CREATED)
def create_debt(data: DebtCreate, db: Session = Depends(get_db)):
    return finance_service.to_debt_read(finance_service.create_debt(db, data))


@router.get("/debts", response_model=list[DebtRead])
def list_debts(db: Session = Depends(get_db)):
    return [finance_service.to_debt_read(debt) for debt in finance_service.list_debts(db)]


@router.get("/debts/{debt_id}", response_model=DebtRead)
def get_debt(debt_id: int, db: Session = Depends(get_db)):
    return finance_service.to_debt_read(_require_debt(db, debt_id))


@router.put("/debts/{debt_id}", response_model=DebtRead)
def update_debt(debt_id: int, data: DebtUpdate, db: Session = Depends(get_db)):
    return finance_service.to_debt_read(
        finance_service.update_debt(db, _require_debt(db, debt_id), data)
    )


@router.post("/debts/{debt_id}/deactivate", response_model=DebtRead)
def deactivate_debt(debt_id: int, db: Session = Depends(get_db)):
    return finance_service.to_debt_read(
        finance_service.set_debt_active(db, _require_debt(db, debt_id), False)
    )


@router.post("/debts/{debt_id}/reactivate", response_model=DebtRead)
def reactivate_debt(debt_id: int, db: Session = Depends(get_db)):
    return finance_service.to_debt_read(
        finance_service.set_debt_active(db, _require_debt(db, debt_id), True)
    )


@router.post("/investments", response_model=InvestmentRead, status_code=status.HTTP_201_CREATED)
def create_investment(data: InvestmentCreate, db: Session = Depends(get_db)):
    return finance_service.to_investment_read(
        finance_service.create_investment(db, data)
    )


@router.get("/investments", response_model=list[InvestmentRead])
def list_investments(db: Session = Depends(get_db)):
    return [
        finance_service.to_investment_read(investment)
        for investment in finance_service.list_investments(db)
    ]


@router.get("/investments/{investment_id}", response_model=InvestmentRead)
def get_investment(investment_id: int, db: Session = Depends(get_db)):
    return finance_service.to_investment_read(_require_investment(db, investment_id))


@router.put("/investments/{investment_id}", response_model=InvestmentRead)
def update_investment(
    investment_id: int, data: InvestmentUpdate, db: Session = Depends(get_db)
):
    return finance_service.to_investment_read(
        finance_service.update_investment(db, _require_investment(db, investment_id), data)
    )


@router.post("/investments/{investment_id}/deactivate", response_model=InvestmentRead)
def deactivate_investment(investment_id: int, db: Session = Depends(get_db)):
    return finance_service.to_investment_read(
        finance_service.set_investment_active(
            db, _require_investment(db, investment_id), False
        )
    )


@router.post("/investments/{investment_id}/reactivate", response_model=InvestmentRead)
def reactivate_investment(investment_id: int, db: Session = Depends(get_db)):
    return finance_service.to_investment_read(
        finance_service.set_investment_active(
            db, _require_investment(db, investment_id), True
        )
    )


@router.get("/finance/summary", response_model=FinanceSummary)
def get_finance_summary(db: Session = Depends(get_db)):
    return finance_service.get_finance_summary(db)