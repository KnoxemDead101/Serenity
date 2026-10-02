"""Authenticated System observations and explicit owner-check evidence API."""

from fastapi import APIRouter, Depends, HTTPException, Path, Request, Response
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError

from auth import require_session
from services.system_health import system_health
from services.data_health import data_health
from services.system_history import history, prepare_observation, record_observation
from storage.database import get_db
from schemas.verification import VerificationCreate, VerificationKind
from services import verification
from services.write_safety import WritesPaused

router = APIRouter(prefix="/serenity-api/system", tags=["System"])


@router.get("/health")
def health(
    request: Request, owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    history_ready = prepare_observation(db, owner_id)
    # A failed PostgreSQL check must not poison the optional audit transaction.
    with db.begin_nested():
        report = system_health(db, application_version=request.app.version)
        # system_health returns fixed evidence on failure; rollback failed SQL
        # before leaving its savepoint so history can still record UNAVAILABLE.
        if report["state"] == "UNAVAILABLE":
            db.get_nested_transaction().rollback()
    report["data_health"] = data_health(
        db, owner_id, readable=report["state"] != "UNAVAILABLE",
    )
    report["history"] = (
        record_observation(db, owner_id, report) if history_ready
        else {"status": "UNAVAILABLE", "recorded": False}
    )
    return JSONResponse(
        report,
        headers={"Cache-Control": "no-store"},
    )


@router.get("/history")
def status_history(
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return JSONResponse(history(db, owner_id), headers={"Cache-Control": "no-store"})


@router.get("/verifications")
def verification_review(
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    try:
        return JSONResponse(verification.review(db, owner_id), headers={"Cache-Control": "no-store"})
    except Exception:
        db.rollback()
        raise HTTPException(503, "Verification evidence could not be read reliably.",
                            headers={"Cache-Control": "no-store"}) from None


@router.put("/verifications/{kind}/{target_id}")
def save_verification(
    kind: VerificationKind, payload: VerificationCreate,
    target_id: int = Path(gt=0), owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    try:
        return JSONResponse(
            verification.save(db, owner_id, kind, target_id, payload),
            headers={"Cache-Control": "no-store"},
        )
    except (HTTPException, WritesPaused):
        raise
    except Exception:
        db.rollback()
        raise HTTPException(503, "The financial snapshot could not be checked reliably.",
                            headers={"Cache-Control": "no-store"}) from None


@router.delete("/verifications/{evidence_id}", status_code=204)
def delete_verification(
    evidence_id: int = Path(gt=0), owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    try:
        verification.remove(db, owner_id, evidence_id)
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(503, "Evidence could not be removed.",
                            headers={"Cache-Control": "no-store"}) from None
    return Response(status_code=204, headers={"Cache-Control": "no-store"})