"""Download routes for owner-scoped Serenity backups and transaction CSVs."""

import json
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

from auth import require_session
from services import export_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/export", tags=["Export"])


def _download(content: str, filename: str, media_type: str) -> Response:
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("")
def export_everything(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return _download(
        json.dumps(export_service.build_export(db, user_id), indent=2),
        f"serenity-backup-{date.today().isoformat()}.json",
        "application/json",
    )


@router.get("/transactions.csv")
def export_transactions_csv(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    return _download(
        export_service.build_transactions_csv(db, user_id),
        f"serenity-transactions-{date.today().isoformat()}.csv",
        "text/csv",
    )