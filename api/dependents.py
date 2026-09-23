"""Dependent label CRUD and soft-lifecycle routes."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from models.dependent import Dependent
from schemas.dependent import DependentCreate, DependentRead, DependentUpdate
from services import dependent_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/dependents", tags=["Dependents"])


def _require(db: Session, dependent_id: int) -> Dependent:
    dependent = dependent_service.get_dependent(db, dependent_id)
    if dependent is None:
        raise HTTPException(status_code=404, detail="Dependent not found")
    return dependent


@router.get("", response_model=list[DependentRead])
def list_dependents(db: Session = Depends(get_db)):
    return [dependent_service.to_dependent_read(x) for x in dependent_service.list_dependents(db)]


@router.post("", response_model=DependentRead, status_code=status.HTTP_201_CREATED)
def create_dependent(data: DependentCreate, db: Session = Depends(get_db)):
    try:
        return dependent_service.to_dependent_read(dependent_service.create_dependent(db, data))
    except dependent_service.NameTakenError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.put("/{dependent_id}", response_model=DependentRead)
def update_dependent(dependent_id: int, data: DependentUpdate, db: Session = Depends(get_db)):
    try:
        return dependent_service.to_dependent_read(
            dependent_service.update_dependent(db, _require(db, dependent_id), data)
        )
    except dependent_service.NameTakenError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@router.post("/{dependent_id}/{action}", response_model=DependentRead)
def set_dependent_active(dependent_id: int, action: str, db: Session = Depends(get_db)):
    if action not in {"deactivate", "reactivate"}:
        raise HTTPException(status_code=404, detail="Dependent action not found")
    return dependent_service.to_dependent_read(
        dependent_service.set_dependent_active(db, _require(db, dependent_id), action == "reactivate")
    )