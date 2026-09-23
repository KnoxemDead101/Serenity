"""Dependent CRUD and soft-lifecycle rules."""

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.dependent import Dependent
from schemas.dependent import DependentCreate, DependentRead, DependentUpdate


class NameTakenError(ValueError):
    """Another dependent already uses this name, case-insensitively."""


def _check_name_free(db: Session, name: str, ignore_id: int | None = None) -> None:
    query = select(Dependent).where(func.lower(Dependent.display_name) == name.lower())
    if ignore_id is not None:
        query = query.where(Dependent.id != ignore_id)
    if db.scalar(query) is not None:
        raise NameTakenError(f'A dependent named "{name}" already exists.')


def create_dependent(db: Session, data: DependentCreate) -> Dependent:
    _check_name_free(db, data.display_name)
    dependent = Dependent(display_name=data.display_name, notes=data.notes)
    db.add(dependent)
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise NameTakenError(f'A dependent named "{data.display_name}" already exists.') from error
    db.refresh(dependent)
    return dependent


def list_dependents(db: Session, active_only: bool = False) -> list[Dependent]:
    query = select(Dependent).order_by(Dependent.display_name)
    if active_only:
        query = query.where(Dependent.active.is_(True))
    return list(db.scalars(query))


def get_dependent(db: Session, dependent_id: int) -> Dependent | None:
    return db.get(Dependent, dependent_id)


def update_dependent(db: Session, dependent: Dependent, data: DependentUpdate) -> Dependent:
    _check_name_free(db, data.display_name, ignore_id=dependent.id)
    dependent.display_name, dependent.notes = data.display_name, data.notes
    try:
        db.commit()
    except IntegrityError as error:
        db.rollback()
        raise NameTakenError(f'A dependent named "{data.display_name}" already exists.') from error
    db.refresh(dependent)
    return dependent


def set_dependent_active(db: Session, dependent: Dependent, active: bool) -> Dependent:
    dependent.active = active
    db.commit()
    db.refresh(dependent)
    return dependent


def to_dependent_read(dependent: Dependent) -> DependentRead:
    return DependentRead.model_validate(dependent, from_attributes=True)