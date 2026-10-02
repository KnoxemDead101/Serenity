"""Goal CRUD and lifecycle rules, isolated from every financial calculation."""

from sqlalchemy import or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import utc_now
from models.goal import Goal
from models.goal_composition import GoalCheckpoint, GoalItem, GoalMilestone
from schemas.goal import GoalCreate, GoalRead, GoalUpdate
from services.ownership import require_owner_id
from utils.choices import (
    GOAL_CATEGORIES, GOAL_PRIORITIES, GOAL_PROGRESS_SOURCES, GOAL_STATUSES, GOAL_TYPES,
)
from utils.money import cents_to_dollars, dollars_to_cents
from utils.validators import require_choice
from models.work import Project


class GoalNotFound(LookupError):
    """Missing and foreign-owned IDs have the same public result."""


class GoalConflict(ValueError):
    """A goal operation conflicts with its lifecycle or related records."""


def get_goal_options() -> dict:
    return {
        "goal_types": GOAL_TYPES,
        "categories": GOAL_CATEGORIES,
        "statuses": GOAL_STATUSES,
        "priorities": GOAL_PRIORITIES,
        "progress_sources": GOAL_PROGRESS_SOURCES,
    }


def get_goal(db: Session, goal_id: int, owner_id: str, *, lock: bool = False) -> Goal | None:
    owner_id = require_owner_id(owner_id)
    if lock and db.get_bind().dialect.name == "sqlite":
        connection = db.connection()
        driver_connection = connection.connection.driver_connection
        if not driver_connection.in_transaction:
            # SQLite ignores FOR UPDATE; reserve the writer lock before reading
            # the Goal so goal-only mutations serialize without global settings.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
    statement = select(Goal).where(
        Goal.id == goal_id, Goal.owner_id == owner_id,
    )
    if lock:
        statement = statement.with_for_update().execution_options(populate_existing=True)
    return db.scalar(statement)


def _require_goal(db: Session, goal_id: int, owner_id: str, *, lock: bool = False) -> Goal:
    goal = get_goal(db, goal_id, owner_id, lock=lock)
    if goal is None:
        raise GoalNotFound("Goal not found")
    return goal


def list_goals(db: Session, owner_id: str, active_only: bool = True) -> list[Goal]:
    query = select(Goal).where(Goal.owner_id == require_owner_id(owner_id))
    if active_only:
        query = query.where(Goal.active.is_(True))
    return list(db.scalars(query.order_by(Goal.name, Goal.id)))


def _editable_values(data: GoalCreate | GoalUpdate) -> dict:
    """Convert optional dollars without turning unknown amounts into zero."""
    values = data.model_dump(exclude={"target_amount", "current_progress_amount"})
    values["target_amount_cents"] = (
        dollars_to_cents(data.target_amount) if data.target_amount is not None else None
    )
    values["current_progress_amount_cents"] = (
        dollars_to_cents(data.current_progress_amount)
        if data.current_progress_amount is not None else None
    )
    return values


def _apply_status(goal: Goal, status: str) -> None:
    """The single backend path that owns status and completion timestamps.

    A repeated COMPLETED request retains the original completion time. Moving
    out of COMPLETED clears it; entering again records a new UTC timestamp.
    Progress amounts never implicitly complete a goal.
    """
    status = require_choice(status, GOAL_STATUSES, "Status")
    if goal.status == status:
        return
    goal.status = status
    goal.completed_at = utc_now() if status == "COMPLETED" else None


def _save(db: Session, goal: Goal) -> Goal:
    db.commit()
    db.refresh(goal)
    return goal


def create_goal(db: Session, data: GoalCreate, owner_id: str) -> Goal:
    goal = Goal(
        owner_id=require_owner_id(owner_id),
        status="NOT_STARTED",
        completed_at=None,
        **_editable_values(data),
    )
    db.add(goal)
    return _save(db, goal)


def update_goal(db: Session, goal_id: int, data: GoalUpdate, owner_id: str) -> Goal:
    """Replace only general fields; status and lifecycle use separate actions."""
    goal = _require_goal(db, goal_id, owner_id, lock=True)
    for field, value in _editable_values(data).items():
        setattr(goal, field, value)
    return _save(db, goal)


def set_goal_active(db: Session, goal_id: int, active: bool, owner_id: str) -> Goal:
    """Archive/reactivate without deleting the goal or changing its status."""
    goal = _require_goal(db, goal_id, owner_id, lock=True)
    goal.active = active
    return _save(db, goal)


def change_goal_status(db: Session, goal_id: int, status: str, owner_id: str) -> Goal:
    goal = _require_goal(db, goal_id, owner_id, lock=True)
    _apply_status(goal, status)
    return _save(db, goal)


def delete_goal(db: Session, goal_id: int, owner_id: str) -> None:
    """Permanent deletion is explicit and never affects other domains."""
    goal = _require_goal(db, goal_id, owner_id, lock=True)
    has_children = db.scalar(select(or_(
        select(GoalItem.id).where(
            GoalItem.goal_id == goal.id,
        ).exists(),
        select(GoalMilestone.id).where(
            GoalMilestone.goal_id == goal.id,
        ).exists(),
        select(GoalCheckpoint.id).where(
            GoalCheckpoint.goal_id == goal.id,
        ).exists(),
        select(Project.id).where(Project.goal_id == goal.id).exists(),
    )))
    if has_children:
        raise GoalConflict("Delete all goal items, milestones, and checkpoints and unlink projects before deleting this goal")
    db.delete(goal)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise GoalConflict("Delete all goal items, milestones, and checkpoints and unlink projects before deleting this goal") from exc


def to_goal_read(goal: Goal) -> GoalRead:
    return GoalRead(
        id=goal.id, name=goal.name, description=goal.description,
        goal_type=goal.goal_type, category=goal.category,
        status=goal.status, priority=goal.priority, target_date=goal.target_date,
        target_amount_cents=goal.target_amount_cents,
        target_amount=(
            cents_to_dollars(goal.target_amount_cents)
            if goal.target_amount_cents is not None else None
        ),
        progress_source=goal.progress_source,
        current_progress_amount_cents=goal.current_progress_amount_cents,
        current_progress_amount=(
            cents_to_dollars(goal.current_progress_amount_cents)
            if goal.current_progress_amount_cents is not None else None
        ),
        notes=goal.notes, active=goal.active, completed_at=goal.completed_at,
        created_at=goal.created_at, updated_at=goal.updated_at,
    )