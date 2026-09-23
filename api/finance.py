from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from schemas.finance import (
    BillCreate,
    BillRead,
    DebtCreate,
    DebtRead,
    FinanceSummary,
    InvestmentCreate,
    InvestmentRead,
)
from services import finance_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api", tags=["Finance"])


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
    bill = finance_service.get_bill(db, bill_id)
    if bill is None:
        raise HTTPException(status_code=404, detail="Bill not found")
    return finance_service.to_bill_read(bill)


@router.post("/debts", response_model=DebtRead, status_code=status.HTTP_201_CREATED)
def create_debt(data: DebtCreate, db: Session = Depends(get_db)):
    return finance_service.to_debt_read(finance_service.create_debt(db, data))


@router.get("/debts", response_model=list[DebtRead])
def list_debts(db: Session = Depends(get_db)):
    return [finance_service.to_debt_read(debt) for debt in finance_service.list_debts(db)]


@router.get("/debts/{debt_id}", response_model=DebtRead)
def get_debt(debt_id: int, db: Session = Depends(get_db)):
    debt = finance_service.get_debt(db, debt_id)
    if debt is None:
        raise HTTPException(status_code=404, detail="Debt not found")
    return finance_service.to_debt_read(debt)


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
    investment = finance_service.get_investment(db, investment_id)
    if investment is None:
        raise HTTPException(status_code=404, detail="Investment not found")
    return finance_service.to_investment_read(investment)


@router.get("/finance/summary", response_model=FinanceSummary)
def get_finance_summary(db: Session = Depends(get_db)):
    return finance_service.get_finance_summary(db)