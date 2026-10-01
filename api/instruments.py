"""Private instrument reference catalog and non-posting trade calculator."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from schemas.instrument import InstrumentCreate, InstrumentRead, InstrumentUpdate, SCALE
from schemas.trading_math import CalculationRead, CalculationRequest
from services import instrument_service, trading_math
from storage.database import get_db

router = APIRouter(prefix="/serenity-api", tags=["Profit Engine"])


def _require_instrument(db: Session, instrument_id: int, owner_id: str):
    instrument = instrument_service.get_instrument(db, instrument_id, owner_id)
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument


@router.get("/instruments", response_model=list[InstrumentRead])
def list_instruments(
    owner_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return [
        instrument_service.to_instrument_read(instrument)
        for instrument in instrument_service.list_instruments(db, owner_id)
    ]


@router.post("/instruments", response_model=InstrumentRead, status_code=status.HTTP_201_CREATED)
def create_instrument(
    data: InstrumentCreate,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    try:
        instrument = instrument_service.create_instrument(db, data, owner_id)
    except instrument_service.InstrumentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    return instrument_service.to_instrument_read(instrument)


@router.get("/instruments/{instrument_id}", response_model=InstrumentRead)
def get_instrument(
    instrument_id: int,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return instrument_service.to_instrument_read(_require_instrument(db, instrument_id, owner_id))


@router.put("/instruments/{instrument_id}", response_model=InstrumentRead)
def update_instrument(
    instrument_id: int,
    data: InstrumentUpdate,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    try:
        instrument = instrument_service.update_instrument(db, instrument_id, data, owner_id)
    except instrument_service.InstrumentConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if instrument is None:
        raise HTTPException(status_code=404, detail="Instrument not found")
    return instrument_service.to_instrument_read(instrument)


@router.get("/instruments/{instrument_id}/specifications", response_model=list[InstrumentRead])
def list_specifications(
    instrument_id: int,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    instrument = _require_instrument(db, instrument_id, owner_id)
    return [
        instrument_service.to_specification_read(specification, instrument)
        for specification in instrument_service.list_specifications(db, instrument_id, owner_id)
    ]


@router.post("/instruments/{instrument_id}/deactivate", response_model=InstrumentRead)
def deactivate_instrument(
    instrument_id: int,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return instrument_service.to_instrument_read(instrument_service.set_instrument_active(
        db, _require_instrument(db, instrument_id, owner_id), False
    ))


@router.post("/instruments/{instrument_id}/reactivate", response_model=InstrumentRead)
def reactivate_instrument(
    instrument_id: int,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return instrument_service.to_instrument_read(instrument_service.set_instrument_active(
        db, _require_instrument(db, instrument_id, owner_id), True
    ))


@router.post("/profit-engine/calculate", response_model=CalculationRead)
def calculate(
    request: CalculationRequest,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    specification = instrument_service.get_specification(db, request.specification_id, owner_id)
    if specification is None:
        raise HTTPException(status_code=404, detail="Instrument specification not found")
    try:
        return trading_math.calculate_trade(
            request,
            asset_type=specification.asset_type,
            tick_size=Decimal(specification.tick_size_units) / SCALE,
            point_value=Decimal(specification.point_value_units) / SCALE,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc