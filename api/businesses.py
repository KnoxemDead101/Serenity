"""Business label CRUD and soft-lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from models.business import Business
from schemas.business import BusinessCreate, BusinessRead, BusinessUpdate
from services import business_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/businesses", tags=["Businesses"])


def _require(db: Session, business_id: int) -> Business:
    business = business_service.get_business(db, business_id)
    if business is None:
        raise HTTPException(status_code=404, detail="Business not found")
    return business


@router.get("", response_model=list[BusinessRead])
def list_businesses(db: Session = Depends(get_db)):
    return [business_service.to_business_read(x) for x in business_service.list_businesses(db)]


@router.post("", response_model=BusinessRead, status_code=status.HTTP_201_CREATED)
def create_business(data: BusinessCreate, db: Session = Depends(get_db)):
    try:
        return business_service.to_business_read(business_service.create_business(db, data))
    except business_service.NameTakenError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/{business_id}", response_model=BusinessRead)
def update_business(business_id: int, data: BusinessUpdate, db: Session = Depends(get_db)):
    try:
        return business_service.to_business_read(
            business_service.update_business(db, _require(db, business_id), data)
        )
    except business_service.NameTakenError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{business_id}/{action}", response_model=BusinessRead)
def set_business_active(business_id: int, action: str, db: Session = Depends(get_db)):
    if action not in {"deactivate", "reactivate"}:
        raise HTTPException(status_code=404, detail="Business action not found")
    return business_service.to_business_read(
        business_service.set_business_active(db, _require(db, business_id), action == "reactivate")
    )