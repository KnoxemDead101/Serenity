"""Thin authenticated work routes, with explicit lifecycle actions."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from auth import require_session
from models.work import Project, Task
from schemas.work import ProjectFields, ProjectRead, TaskFields, TaskRead, WorkStatusChange
from services import work_service
from storage.database import get_db


def _call(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except work_service.WorkNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except work_service.WorkConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _router(model, payload_schema, read_schema, plural):
    """Both work families share the same lifecycle, not financial behavior."""
    router = APIRouter(prefix=f"/serenity-api/{plural}", tags=[plural.title()])

    def read(db, record, owner_id):
        return work_service.read_work(db, model, [record], owner_id)[0]

    @router.get("/options")
    def options(owner_id: str = Depends(require_session)):
        return work_service.get_options()

    @router.get("", response_model=list[read_schema])
    def list_records(
        active_only: bool = True,
        goal_id: int | None = Query(default=None, gt=0, le=2147483647),
        project_id: int | None = Query(default=None, gt=0, le=2147483647),
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        if (model is Project and project_id is not None) or (model is Task and goal_id is not None):
            raise HTTPException(status_code=422, detail="Unsupported source filter")
        source_id = goal_id if model is Project else project_id
        records = _call(
            work_service.list_work, db, model, owner_id,
            active_only=active_only, source_id=source_id,
        )
        return work_service.read_work(db, model, records, owner_id)

    @router.post("", response_model=read_schema, status_code=201)
    def create_record(
        data: payload_schema,
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        return read(db, _call(work_service.create_work, db, model, data, owner_id), owner_id)

    @router.get("/{record_id}", response_model=read_schema)
    def get_record(
        record_id: int,
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        return read(db, _call(work_service.get_work, db, model, record_id, owner_id), owner_id)

    @router.put("/{record_id}", response_model=read_schema)
    def update_record(
        record_id: int, data: payload_schema,
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        return read(db, _call(
            work_service.update_work, db, model, record_id, data, owner_id,
        ), owner_id)

    @router.post("/{record_id}/status", response_model=read_schema)
    def status_record(
        record_id: int, data: WorkStatusChange,
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        return read(db, _call(
            work_service.set_status, db, model, record_id, data.status, owner_id,
        ), owner_id)

    @router.post("/{record_id}/deactivate", response_model=read_schema)
    def archive_record(
        record_id: int,
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        return read(db, _call(
            work_service.set_active, db, model, record_id, False, owner_id,
        ), owner_id)

    @router.post("/{record_id}/reactivate", response_model=read_schema)
    def restore_record(
        record_id: int,
        owner_id: str = Depends(require_session), db: Session = Depends(get_db),
    ):
        return read(db, _call(
            work_service.set_active, db, model, record_id, True, owner_id,
        ), owner_id)

    return router


projects_router = _router(Project, ProjectFields, ProjectRead, "projects")
tasks_router = _router(Task, TaskFields, TaskRead, "tasks")