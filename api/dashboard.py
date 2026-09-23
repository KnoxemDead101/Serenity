"""
Dashboard API routes.

    GET /serenity-api/dashboard/summary   totals calculated from stored records

The dashboard never stores its own numbers. It asks the services to
calculate them fresh from the real records every time.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from schemas.dashboard import DashboardSummary
from services import dashboard_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummary)
def get_summary(db: Session = Depends(get_db)):
    return dashboard_service.get_dashboard_summary(db)
