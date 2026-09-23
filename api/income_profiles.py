"""Authenticated API routes for owner-scoped Income Profiles."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from models.income_profile import IncomeProfile
from schemas.income_profile import (
    IncomeProfileCreate,
    IncomeProfileRead,
    IncomeProfileUpdate,
    IncomeSummary,
)
from services import income_profile_service as service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/income-profiles", tags=["Income Profiles"])


def _require_profile(db: Session, profile_id: int, owner_id: str) -> IncomeProfile:
    profile = service.get_income_profile(db, profile_id, owner_id)
    if profile is None:
        raise HTTPException(status_code=404, detail="Income profile not found")
    return profile


@router.get("/options")
def income_options():
    return service.get_income_options()


@router.get("/summary", response_model=IncomeSummary)
def income_summary(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return service.get_income_summary(db, user_id)


@router.get("", response_model=list[IncomeProfileRead])
def list_profiles(user_id: str = Depends(require_session), db: Session = Depends(get_db)):
    return [
        service.to_income_profile_read(profile)
        for profile in service.list_income_profiles(db, user_id)
    ]


@router.post("", response_model=IncomeProfileRead, status_code=status.HTTP_201_CREATED)
def create_profile(
    data: IncomeProfileCreate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return service.to_income_profile_read(
        service.create_income_profile(db, data, user_id)
    )


@router.get("/{profile_id}", response_model=IncomeProfileRead)
def get_profile(
    profile_id: int, user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return service.to_income_profile_read(_require_profile(db, profile_id, user_id))


@router.put("/{profile_id}", response_model=IncomeProfileRead)
def update_profile(
    profile_id: int,
    data: IncomeProfileUpdate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    profile = _require_profile(db, profile_id, user_id)
    return service.to_income_profile_read(
        service.update_income_profile(db, profile, data)
    )


@router.post("/{profile_id}/deactivate", response_model=IncomeProfileRead)
def deactivate_profile(
    profile_id: int, user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    profile = _require_profile(db, profile_id, user_id)
    return service.to_income_profile_read(
        service.set_income_profile_active(db, profile, False)
    )


@router.post("/{profile_id}/reactivate", response_model=IncomeProfileRead)
def reactivate_profile(
    profile_id: int, user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    profile = _require_profile(db, profile_id, user_id)
    return service.to_income_profile_read(
        service.set_income_profile_active(db, profile, True)
    )