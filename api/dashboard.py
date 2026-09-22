"""
Dashboard API routes.

    GET /api/dashboard/summary   totals calculated from stored records

The dashboard never stores its own numbers. It asks the services to
calculate them fresh from the real records every time.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from schemas.account import AccountTotals
from services import account_service
from storage.database import get_db

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=AccountTotals)
def get_summary(db: Session = Depends(get_db)):
    return account_service.get_account_totals(db)
