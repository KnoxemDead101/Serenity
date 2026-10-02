"""Authenticated read-only preview endpoints; deliberately no execute endpoint."""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth import require_session
from schemas.reconciliation import PreviewRequest, ReportToken
from services import reconciliation_service as service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/reconciliation", tags=["Reconciliation preview"])


def _call(operation, *args):
    try:
        return operation(*args)
    except service.ReconciliationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.StaleReport as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Preview signing is unavailable") from exc


@router.post("/preview")
def preview(data: PreviewRequest, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    result = _call(service.build_preview, db, owner_id, data)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/execution-preview")
def execution_preview(
    data: PreviewRequest, owner_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    result = _call(service.build_execution_preview, db, owner_id, data)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/verify")
def verify(data: ReportToken, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    result = _call(service.verify_report, db, owner_id, data.report_token)
    return JSONResponse(result, headers={"Cache-Control": "no-store"})


@router.post("/export")
def export(data: ReportToken, owner_id: str = Depends(require_session), db: Session = Depends(get_db)):
    result = _call(service.export_report, db, owner_id, data.report_token)
    return JSONResponse(result, headers={
        "Cache-Control": "no-store",
        "Content-Disposition": 'attachment; filename="serenity-reconciliation-preview.json"',
    })