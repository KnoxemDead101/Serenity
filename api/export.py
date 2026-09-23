"""Download routes for complete Serenity backups and transaction CSVs.

These endpoints intentionally have no authentication layer because Serenity
currently has no user accounts.  Anyone who can reach the app can download
the financial data, so deployment access control must be configured before
real data is used.
"""

import json
from datetime import date

from fastapi import APIRouter, Depends
from fastapi.responses import Response
from sqlalchemy.orm import Session

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
def export_everything(db: Session = Depends(get_db)):
    return _download(
        json.dumps(export_service.build_export(db), indent=2),
        f"serenity-backup-{date.today().isoformat()}.json",
        "application/json",
    )


@router.get("/transactions.csv")
def export_transactions_csv(db: Session = Depends(get_db)):
    return _download(
        export_service.build_transactions_csv(db),
        f"serenity-transactions-{date.today().isoformat()}.csv",
        "text/csv",
    )