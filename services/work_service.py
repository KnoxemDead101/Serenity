"""Projects and Tasks track work only; no financial service is called here."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import utc_now
from models.goal import Goal
from models.work import Project, Task, WORK_PRIORITIES, WORK_STATUSES
from schemas.work import ProjectFields, ProjectRead, TaskFields, TaskRead
from services.goal_service import get_goal
from services.ownership import require_owner_id
from utils.validators import require_choice


class WorkNotFound(LookupError):
    """Missing and foreign-owned work/source IDs have identical responses."""


class WorkConflict(ValueError):
    """Archived source or concurrent relationship changes prevent a write."""


def get_options() -> dict:
    return {"statuses": WORK_STATUSES, "priorities": WORK_PRIORITIES}


def _reserve_sqlite_writer(db: Session) -> None:
    if db.get_bind().dialect.name == "sqlite":
        connection = db.connection()
        if not connection.connection.driver_connection.in_transaction:
            # SQLite ignores FOR UPDATE. Reserve before reading any work/source.
            connection.exec_driver_sql("BEGIN IMMEDIATE")


def get_work(db: Session, model, record_id: int, owner_id: str, *, lock=False):
    if lock:
        _reserve_sqlite_writer(db)
    query = select(model).where(
        model.id == record_id, model.owner_id == require_owner_id(owner_id),
    )
    if lock:
        query = query.with_for_update().execution_options(populate_existing=True)
    record = db.scalar(query)
    if record is None:
        raise WorkNotFound(f"{model.__name__} not found")
    return record


def _source(db, model, source_id, owner_id, *, lock=False):
    if model is Project:
        source = get_goal(db, source_id, owner_id, lock=lock)
        if source is None:
            raise WorkNotFound("Goal not found")
        return source
    return get_work(db, Project, source_id, owner_id, lock=lock)


def list_work(db, model, owner_id, *, active_only=True, source_id=None):
    owner_id = require_owner_id(owner_id)
    query = select(model).where(model.owner_id == owner_id)
    if source_id is not None:
        _source(db, model, source_id, owner_id)
        link = model.goal_id if model is Project else model.project_id
        query = query.where(link == source_id)
    if active_only:
        query = query.where(model.active.is_(True))
    return list(db.scalars(query.order_by(model.name, model.id)))


def _validate_link(db, model, source_id, owner_id, *, require_active=True):
    if source_id is not None:
        source = _source(db, model, source_id, owner_id, lock=True)
        if require_active and not source.active:
            raise WorkConflict(f"Reactivate the {type(source).__name__.lower()} before linking or changing work")


def _save(db, record):
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise WorkConflict("The work relationship changed. Reload and try again.") from exc
    db.refresh(record)
    return record


def create_work(db, model, data: ProjectFields | TaskFields, owner_id):
    owner_id = require_owner_id(owner_id)
    _reserve_sqlite_writer(db)
    link = data.goal_id if model is Project else data.project_id
    _validate_link(db, model, link, owner_id)
    record = model(owner_id=owner_id, **data.model_dump())
    db.add(record)
    return _save(db, record)


def _mutable_record(db, model, record_id, owner_id, *, allow_archived=False):
    record = get_work(db, model, record_id, owner_id, lock=True)
    if not allow_archived and not record.active:
        raise WorkConflict(f"Reactivate the {model.__name__.lower()} before editing it")
    if model is Task:
        # Parent archive is independent of child status and archive state.
        _validate_link(db, Task, record.project_id, owner_id)
    return record


def update_work(db, model, record_id, data, owner_id):
    record = _mutable_record(db, model, record_id, owner_id)
    link_name = "goal_id" if model is Project else "project_id"
    source_id = getattr(data, link_name)
    # Archived Goals remain valid historical sources for an existing Project.
    # New or changed links require an active source; Tasks require active Projects.
    _validate_link(
        db, model, source_id, owner_id,
        require_active=model is Task or source_id != getattr(record, link_name),
    )
    for field, value in data.model_dump().items():
        setattr(record, field, value)
    return _save(db, record)


def set_active(db, model, record_id, active, owner_id):
    record = _mutable_record(db, model, record_id, owner_id, allow_archived=True)
    record.active = active
    return _save(db, record)


def set_status(db, model, record_id, status, owner_id):
    status = require_choice(status, WORK_STATUSES, "Status")
    record = _mutable_record(db, model, record_id, owner_id)
    if record.status != status:
        record.status = status
        record.completed_at = utc_now() if status == "COMPLETED" else None
    return _save(db, record)


def read_work(db, model, records, owner_id):
    """Load source names in one owner-scoped query, not one query per record."""
    link_name = "goal_id" if model is Project else "project_id"
    source_model = Goal if model is Project else Project
    source_ids = {getattr(record, link_name) for record in records} - {None}
    names = dict(db.execute(select(source_model.id, source_model.name).where(
        source_model.owner_id == require_owner_id(owner_id),
        source_model.id.in_(source_ids),
    )).all()) if source_ids else {}
    schema = ProjectRead if model is Project else TaskRead
    result = []
    for record in records:
        values = {column.name: getattr(record, column.name) for column in model.__table__.columns
                  if column.name != "owner_id"}
        values["goal_name" if model is Project else "project_name"] = names.get(
            getattr(record, link_name),
        )
        result.append(schema(**values))
    return result