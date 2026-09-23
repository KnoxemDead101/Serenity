"""Business CRUD and soft-lifecycle rules."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.business import Business
from schemas.business import BusinessCreate, BusinessRead, BusinessUpdate


class NameTakenError(ValueError):
    """Another business already uses this name, case-insensitively."""


def _check_name_free(db: Session, name: str, ignore_id: int | None = None) -> None:
    query = select(Business).where(func.lower(Business.name) == name.lower())
    if ignore_id is not None:
        query = query.where(Business.id != ignore_id)
    if db.scalar(query) is not None:
        raise NameTakenError(f'A business named "{name}" already exists.')


def create_business(db: Session, data: BusinessCreate) -> Business:
    _check_name_free(db, data.name)
    business = Business(name=data.name, notes=data.notes)
    db.add(business)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise NameTakenError(f'A business named "{data.name}" already exists.') from error
    db.refresh(business)
    return business


def list_businesses(db: Session, active_only: bool = False) -> list[Business]:
    query = select(Business).order_by(Business.name)
    if active_only:
        query = query.where(Business.active.is_(True))
    return list(db.scalars(query))


def get_business(db: Session, business_id: int) -> Business | None:
    return db.get(Business, business_id)


def update_business(db: Session, business: Business, data: BusinessUpdate) -> Business:
    _check_name_free(db, data.name, ignore_id=business.id)
    business.name, business.notes = data.name, data.notes
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise NameTakenError(f'A business named "{data.name}" already exists.') from error
    db.refresh(business)
    return business


def set_business_active(db: Session, business: Business, active: bool) -> Business:
    business.active = active
    db.commit()
    db.refresh(business)
    return business


def to_business_read(business: Business) -> BusinessRead:
    return BusinessRead.model_validate(business, from_attributes=True)