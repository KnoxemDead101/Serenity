"""Owner-scoped goal items, milestones, and checkpoints."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import utc_now
from models.goal import Goal
from models.goal_composition import GoalCheckpoint, GoalItem, GoalMilestone
from schemas.goal_composition import (
    GoalCheckpointCreate, GoalCheckpointRead, GoalCheckpointUpdate,
    GoalCompositionRead, GoalItemCreate, GoalItemRead, GoalItemUpdate,
    GoalMilestoneCreate, GoalMilestoneRead, GoalMilestoneUpdate,
)
from services import goal_service
from utils.choices import GOAL_ITEM_STATUSES, GOAL_MILESTONE_STATUSES
from utils.money import cents_to_dollars, dollars_to_cents
from utils.validators import require_choice


class CompositionNotFound(LookupError):
    """A composition record is missing or belongs to another owner or goal."""


def get_composition_options() -> dict:
    return {
        "item_statuses": GOAL_ITEM_STATUSES,
        "milestone_statuses": GOAL_MILESTONE_STATUSES,
    }


def _require_active_parent(db: Session, goal_id: int, owner_id: str) -> Goal:
    goal = goal_service._require_goal(db, goal_id, owner_id, lock=True)
    if not goal.active:
        raise goal_service.GoalConflict("Goal is inactive")
    return goal


def _commit(db: Session, message: str) -> None:
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise goal_service.GoalConflict(message) from exc


def _save(db: Session, row):
    _commit(db, "Could not save goal composition record")
    db.refresh(row)
    return row


def _require_record(db: Session, model, goal: Goal, record_id: int):
    row = db.scalar(select(model).where(
        model.owner_id == goal.owner_id,
        model.goal_id == goal.id,
        model.id == record_id,
    ))
    if row is None:
        raise CompositionNotFound("Goal composition record not found")
    return row


def _money_values(data, field_names: tuple[str, ...]) -> dict:
    values = data.model_dump(exclude=set(field_names))
    for field in field_names:
        amount = getattr(data, field)
        cents_field = f"{field}_cents"
        values[cents_field] = dollars_to_cents(amount) if amount is not None else None
    return values


def to_item_read(row: GoalItem) -> GoalItemRead:
    return GoalItemRead(
        id=row.id, goal_id=row.goal_id, name=row.name, description=row.description,
        expected_cost_cents=row.expected_cost_cents,
        expected_cost=(
            cents_to_dollars(row.expected_cost_cents)
            if row.expected_cost_cents is not None else None
        ),
        manual_actual_cost_override_cents=row.manual_actual_cost_override_cents,
        manual_actual_cost_override=(
            cents_to_dollars(row.manual_actual_cost_override_cents)
            if row.manual_actual_cost_override_cents is not None else None
        ),
        notes=row.notes, status=row.status, active=row.active,
        sort_order=row.sort_order, created_at=row.created_at, updated_at=row.updated_at,
    )


def to_milestone_read(row: GoalMilestone) -> GoalMilestoneRead:
    return GoalMilestoneRead(
        id=row.id, goal_id=row.goal_id, title=row.title, description=row.description,
        target_date=row.target_date, status=row.status, completed_at=row.completed_at,
        sort_order=row.sort_order, created_at=row.created_at, updated_at=row.updated_at,
    )


def to_checkpoint_read(row: GoalCheckpoint, goal: Goal) -> GoalCheckpointRead:
    meaningful_progress = (
        goal.progress_source == "MANUAL"
        and goal.current_progress_amount_cents is not None
    )
    return GoalCheckpointRead(
        id=row.id, goal_id=row.goal_id, amount_cents=row.amount_cents,
        amount=cents_to_dollars(row.amount_cents), label=row.label,
        reached=(
            goal.current_progress_amount_cents >= row.amount_cents
            if meaningful_progress else None
        ),
        sort_order=row.sort_order, created_at=row.created_at, updated_at=row.updated_at,
    )


def list_goal_items(
    db: Session, goal_id: int, owner_id: str, active_only: bool = True,
) -> list[GoalItemRead]:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    query = select(GoalItem).where(
        GoalItem.owner_id == goal.owner_id, GoalItem.goal_id == goal.id,
    )
    if active_only:
        query = query.where(GoalItem.active.is_(True))
    return [to_item_read(row) for row in db.scalars(
        query.order_by(GoalItem.sort_order, GoalItem.id)
    )]


def get_goal_item(db: Session, goal_id: int, record_id: int, owner_id: str) -> GoalItemRead:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    return to_item_read(_require_record(db, GoalItem, goal, record_id))


def create_goal_item(
    db: Session, goal_id: int, data: GoalItemCreate, owner_id: str,
) -> GoalItemRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = GoalItem(
        owner_id=goal.owner_id, goal_id=goal.id,
        **_money_values(data, ("expected_cost", "manual_actual_cost_override")),
    )
    db.add(row)
    return to_item_read(_save(db, row))


def update_goal_item(
    db: Session, goal_id: int, record_id: int, data: GoalItemUpdate, owner_id: str,
) -> GoalItemRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = _require_record(db, GoalItem, goal, record_id)
    for field, value in _money_values(
        data, ("expected_cost", "manual_actual_cost_override"),
    ).items():
        setattr(row, field, value)
    return to_item_read(_save(db, row))


def delete_goal_item(db: Session, goal_id: int, record_id: int, owner_id: str) -> None:
    goal = _require_active_parent(db, goal_id, owner_id)
    db.delete(_require_record(db, GoalItem, goal, record_id))
    _commit(db, "Could not delete goal item")


def change_goal_item_status(
    db: Session, goal_id: int, record_id: int, status: str, owner_id: str,
) -> GoalItemRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = _require_record(db, GoalItem, goal, record_id)
    row.status = require_choice(status, GOAL_ITEM_STATUSES, "Status")
    return to_item_read(_save(db, row))


def set_goal_item_active(
    db: Session, goal_id: int, record_id: int, active: bool, owner_id: str,
) -> GoalItemRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = _require_record(db, GoalItem, goal, record_id)
    row.active = active
    return to_item_read(_save(db, row))


def list_goal_milestones(db: Session, goal_id: int, owner_id: str) -> list[GoalMilestoneRead]:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    rows = db.scalars(select(GoalMilestone).where(
        GoalMilestone.owner_id == goal.owner_id, GoalMilestone.goal_id == goal.id,
    ).order_by(GoalMilestone.sort_order, GoalMilestone.id))
    return [to_milestone_read(row) for row in rows]


def get_goal_milestone(
    db: Session, goal_id: int, record_id: int, owner_id: str,
) -> GoalMilestoneRead:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    return to_milestone_read(_require_record(db, GoalMilestone, goal, record_id))


def create_goal_milestone(
    db: Session, goal_id: int, data: GoalMilestoneCreate, owner_id: str,
) -> GoalMilestoneRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = GoalMilestone(owner_id=goal.owner_id, goal_id=goal.id, **data.model_dump())
    db.add(row)
    return to_milestone_read(_save(db, row))


def update_goal_milestone(
    db: Session, goal_id: int, record_id: int,
    data: GoalMilestoneUpdate, owner_id: str,
) -> GoalMilestoneRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = _require_record(db, GoalMilestone, goal, record_id)
    for field, value in data.model_dump().items():
        setattr(row, field, value)
    return to_milestone_read(_save(db, row))


def delete_goal_milestone(db: Session, goal_id: int, record_id: int, owner_id: str) -> None:
    goal = _require_active_parent(db, goal_id, owner_id)
    db.delete(_require_record(db, GoalMilestone, goal, record_id))
    _commit(db, "Could not delete goal milestone")


def change_goal_milestone_status(
    db: Session, goal_id: int, record_id: int,
    status: str, owner_id: str,
) -> GoalMilestoneRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = _require_record(db, GoalMilestone, goal, record_id)
    next_status = require_choice(status, GOAL_MILESTONE_STATUSES, "Status")
    if row.status != next_status:
        row.status = next_status
        row.completed_at = utc_now() if next_status == "COMPLETED" else None
    return to_milestone_read(_save(db, row))


def list_goal_checkpoints(db: Session, goal_id: int, owner_id: str) -> list[GoalCheckpointRead]:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    rows = db.scalars(select(GoalCheckpoint).where(
        GoalCheckpoint.owner_id == goal.owner_id, GoalCheckpoint.goal_id == goal.id,
    ).order_by(GoalCheckpoint.sort_order, GoalCheckpoint.id))
    return [to_checkpoint_read(row, goal) for row in rows]


def get_goal_checkpoint(
    db: Session, goal_id: int, record_id: int, owner_id: str,
) -> GoalCheckpointRead:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    row = _require_record(db, GoalCheckpoint, goal, record_id)
    return to_checkpoint_read(row, goal)


def create_goal_checkpoint(
    db: Session, goal_id: int, data: GoalCheckpointCreate, owner_id: str,
) -> GoalCheckpointRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    values = data.model_dump(exclude={"amount"})
    values["amount_cents"] = dollars_to_cents(data.amount)
    row = GoalCheckpoint(owner_id=goal.owner_id, goal_id=goal.id, **values)
    db.add(row)
    return to_checkpoint_read(_save(db, row), goal)


def update_goal_checkpoint(
    db: Session, goal_id: int, record_id: int,
    data: GoalCheckpointUpdate, owner_id: str,
) -> GoalCheckpointRead:
    goal = _require_active_parent(db, goal_id, owner_id)
    row = _require_record(db, GoalCheckpoint, goal, record_id)
    values = data.model_dump(exclude={"amount"})
    values["amount_cents"] = dollars_to_cents(data.amount)
    for field, value in values.items():
        setattr(row, field, value)
    return to_checkpoint_read(_save(db, row), goal)


def delete_goal_checkpoint(db: Session, goal_id: int, record_id: int, owner_id: str) -> None:
    goal = _require_active_parent(db, goal_id, owner_id)
    db.delete(_require_record(db, GoalCheckpoint, goal, record_id))
    _commit(db, "Could not delete goal checkpoint")


def get_goal_composition(
    db: Session, goal_id: int, owner_id: str, active_only: bool = True,
) -> GoalCompositionRead:
    goal = goal_service._require_goal(db, goal_id, owner_id)
    item_query = select(GoalItem).where(
        GoalItem.owner_id == goal.owner_id, GoalItem.goal_id == goal.id,
    )
    if active_only:
        item_query = item_query.where(GoalItem.active.is_(True))
    items = db.scalars(item_query.order_by(GoalItem.sort_order, GoalItem.id))
    milestones = db.scalars(select(GoalMilestone).where(
        GoalMilestone.owner_id == goal.owner_id, GoalMilestone.goal_id == goal.id,
    ).order_by(GoalMilestone.sort_order, GoalMilestone.id))
    checkpoints = db.scalars(select(GoalCheckpoint).where(
        GoalCheckpoint.owner_id == goal.owner_id, GoalCheckpoint.goal_id == goal.id,
    ).order_by(GoalCheckpoint.sort_order, GoalCheckpoint.id))
    return GoalCompositionRead(
        goal=goal_service.to_goal_read(goal),
        items=[to_item_read(row) for row in items],
        milestones=[to_milestone_read(row) for row in milestones],
        checkpoints=[to_checkpoint_read(row, goal) for row in checkpoints],
    )