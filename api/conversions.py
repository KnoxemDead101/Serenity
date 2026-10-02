"""Owner-private conversion approval and audit endpoints."""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from auth import current_user, require_session
from schemas.conversion import ApprovalRequest, ExecuteRequest, ReverseRequest
from services import conversion_service as service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/conversions", tags=["Investment conversions"])


def _response(value, status_code=200, attachment=None):
    headers = {"Cache-Control": "no-store"}
    if attachment:
        headers["Content-Disposition"] = f'attachment; filename="{attachment}"'
    return JSONResponse(jsonable_encoder(value), status_code=status_code, headers=headers)


def _call(operation, *args):
    try:
        return operation(*args)
    except service.ConversionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.BackupEvidenceUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.ConversionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.reconciliation_service.ReconciliationNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail="Conversion authorization is unavailable") from exc


@router.post("/approvals", status_code=201)
def create_approval(
    data: ApprovalRequest,
    request: Request,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    actor = current_user(request) or owner_id
    return _response(_call(service.approve, db, owner_id, actor, data), status_code=201)


@router.get("/review-context")
def review_context(
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return _response(_call(service.review_context, db, owner_id))


@router.post("/{approval_id}/execute")
def execute(
    approval_id: int,
    data: ExecuteRequest,
    request: Request,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    actor = current_user(request) or owner_id
    return _response(_call(service.execute, db, owner_id, actor, approval_id, data))


@router.get("/{approval_id}")
def evidence(
    approval_id: int,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return _response(_call(service.get_evidence, db, owner_id, approval_id))


@router.get("/{approval_id}/evidence")
def evidence_export(
    approval_id: int,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return _response(
        _call(service.get_evidence, db, owner_id, approval_id),
        attachment=f"serenity-conversion-{approval_id}-evidence.json",
    )


@router.post("/{approval_id}/reverse")
def reverse(
    approval_id: int,
    data: ReverseRequest,
    request: Request,
    owner_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    if not data.confirm_reverse:
        raise HTTPException(status_code=422, detail="Explicit reversal confirmation is required")
    actor = current_user(request) or owner_id
    return _response(_call(
        service.reverse, db, owner_id, actor, approval_id, data.reason,
    ))