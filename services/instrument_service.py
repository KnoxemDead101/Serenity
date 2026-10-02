"""Workspace-scoped reference instruments; specifications are append-only."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import utc_now
from models.instrument import Instrument, InstrumentSpecification
from schemas.instrument import InstrumentCreate, InstrumentRead, InstrumentUpdate, SCALE, spec_units
from services.financial_write_lock import lock_owner_financial_writes
from services.ownership import require_owner_id


class InstrumentConflictError(ValueError):
    """A workspace already owns the symbol, or a simultaneous update won."""


def list_instruments(db: Session, owner_id: str) -> list[Instrument]:
    return list(db.scalars(
        select(Instrument).where(Instrument.owner_id == require_owner_id(owner_id))
        .order_by(Instrument.symbol)
    ))


def get_instrument(db: Session, instrument_id: int, owner_id: str, *, lock=False) -> Instrument | None:
    statement = select(Instrument).where(
        Instrument.id == instrument_id, Instrument.owner_id == require_owner_id(owner_id)
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def get_specification(
    db: Session, specification_id: int, owner_id: str
) -> InstrumentSpecification | None:
    owner_id = require_owner_id(owner_id)
    return db.scalar(
        select(InstrumentSpecification)
        .join(Instrument, Instrument.id == InstrumentSpecification.instrument_id)
        .where(
            InstrumentSpecification.id == specification_id,
            InstrumentSpecification.owner_id == owner_id,
            Instrument.owner_id == owner_id,
        )
    )


def list_specifications(
    db: Session, instrument_id: int, owner_id: str
) -> list[InstrumentSpecification]:
    owner_id = require_owner_id(owner_id)
    return list(db.scalars(select(InstrumentSpecification).where(
        InstrumentSpecification.instrument_id == instrument_id,
        InstrumentSpecification.owner_id == owner_id,
    ).order_by(InstrumentSpecification.version)))


def _new_specification(
    instrument: Instrument, data: InstrumentCreate | InstrumentUpdate, version: int
) -> InstrumentSpecification:
    return InstrumentSpecification(
        instrument=instrument,
        owner_id=instrument.owner_id,
        version=version,
        symbol=data.symbol,
        name=data.name,
        asset_type=data.asset_type,
        exchange=data.exchange,
        currency=data.currency,
        tick_size_units=spec_units(data.tick_size, "Tick size"),
        point_value_units=spec_units(data.point_value, "Point value"),
    )


def _commit(db: Session) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise InstrumentConflictError(
            "This instrument symbol already exists or was changed concurrently"
        ) from exc


def create_instrument(db: Session, data: InstrumentCreate, owner_id: str) -> Instrument:
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    instrument = Instrument(owner_id=owner_id, symbol=data.symbol)
    db.add(instrument)
    db.add(_new_specification(instrument, data, 1))
    _commit(db)
    db.refresh(instrument)
    return instrument


def update_instrument(
    db: Session, instrument_id: int, data: InstrumentUpdate, owner_id: str
) -> Instrument | None:
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    instrument = get_instrument(db, instrument_id, owner_id, lock=True)
    if instrument is None:
        return None
    if data.symbol != instrument.symbol:
        raise ValueError("An instrument symbol cannot be changed")
    latest = db.scalar(
        select(InstrumentSpecification)
        .where(
            InstrumentSpecification.instrument_id == instrument.id,
            InstrumentSpecification.owner_id == owner_id,
        )
        .order_by(InstrumentSpecification.version.desc())
        .limit(1)
        .execution_options(populate_existing=True)
    )
    if latest is None:
        raise InstrumentConflictError("Instrument has no specification to update")
    if data.asset_type != latest.asset_type:
        raise ValueError("An instrument type cannot be changed")
    db.add(_new_specification(instrument, data, latest.version + 1))
    instrument.updated_at = utc_now()
    _commit(db)
    db.expire(instrument, ["specifications"])
    return instrument


def set_instrument_active(
    db: Session, instrument: Instrument, active: bool
) -> Instrument:
    owner_id = require_owner_id(instrument.owner_id)
    lock_owner_financial_writes(db, owner_id)
    instrument = get_instrument(db, instrument.id, owner_id, lock=True)
    if instrument is None:
        raise ValueError("Instrument no longer exists for this owner")
    instrument.active = active
    _commit(db)
    db.refresh(instrument)
    return instrument


def to_instrument_read(instrument: Instrument) -> InstrumentRead:
    latest = instrument.specifications[-1]
    return InstrumentRead(
        id=instrument.id,
        specification_id=latest.id,
        version=latest.version,
        symbol=instrument.symbol,
        name=latest.name,
        asset_type=latest.asset_type,
        exchange=latest.exchange,
        currency=latest.currency,
        tick_size=Decimal(latest.tick_size_units) / SCALE,
        point_value=Decimal(latest.point_value_units) / SCALE,
        active=instrument.active,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
    )


def to_specification_read(
    specification: InstrumentSpecification, instrument: Instrument
) -> InstrumentRead:
    return InstrumentRead(
        id=instrument.id,
        specification_id=specification.id,
        version=specification.version,
        symbol=specification.symbol,
        name=specification.name,
        asset_type=specification.asset_type,
        exchange=specification.exchange,
        currency=specification.currency,
        tick_size=Decimal(specification.tick_size_units) / SCALE,
        point_value=Decimal(specification.point_value_units) / SCALE,
        active=instrument.active,
        created_at=instrument.created_at,
        updated_at=instrument.updated_at,
    )