"""Owner-matched planning facts, never financial activity or progress caches."""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint,
    Index, Integer, String, Text, true,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from models.goal_composition_sqlite import register_sqlite_goal_guards
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base
from utils.choices import GOAL_ITEM_STATUSES, GOAL_MILESTONE_STATUSES


def _parent_constraints(table: str) -> tuple:
    """Match both workspace and Goal, using the existing container convention."""
    return (
        ForeignKeyConstraint(
            ["owner_id", "goal_id"], ["goals.owner_id", "goals.id"],
            name=f"fk_{table}_owner_goal", ondelete="RESTRICT",
        ),
        Index(f"ix_{table}_owner_goal_order", "owner_id", "goal_id", "sort_order", "id"),
        # Deletion guards check every child by Goal ID, including malformed
        # metadata, without scanning unrelated owners' planning records.
        Index(f"ix_{table}_goal_id", "goal_id"),
        CheckConstraint(
            "sort_order BETWEEN 0 AND 2147483647", name=f"ck_{table}_sort_order",
        ),
    )


def _money_constraint(table: str, column: str, optional: bool = True) -> CheckConstraint:
    expression = f"{column} BETWEEN 0 AND 100000000000000"
    if optional:
        expression = f"{column} IS NULL OR {expression}"
    return CheckConstraint(expression, name=f"ck_{table}_{column}")


def _status_constraint(table: str, choices: list[str]) -> CheckConstraint:
    values = ", ".join(f"'{value}'" for value in choices)
    return CheckConstraint(f"status IN ({values})", name=f"ck_{table}_status")


class GoalCompositionFields:
    """Shared identity, stable ordering and UTC timestamps; no ORM cascades."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    goal_id: Mapped[int] = mapped_column(Integer, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now,
    )


class GoalItem(GoalCompositionFields, Base):
    __tablename__ = "goal_items"
    __table_args__ = (
        *_parent_constraints("goal_items"),
        _status_constraint("goal_items", GOAL_ITEM_STATUSES),
        _money_constraint("goal_items", "expected_cost_cents"),
        _money_constraint("goal_items", "manual_actual_cost_override_cents"),
    )

    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    expected_cost_cents: Mapped[int | None] = mapped_column(BigInteger)
    # Provisional planning input, not spending. Future linked Transaction-derived
    # actual cost must take precedence over this override, never be added to it.
    manual_actual_cost_override_cents: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(
        String(16), default="PLANNED", server_default="PLANNED",
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())


class GoalMilestone(GoalCompositionFields, Base):
    __tablename__ = "goal_milestones"
    __table_args__ = (
        *_parent_constraints("goal_milestones"),
        _status_constraint("goal_milestones", GOAL_MILESTONE_STATUSES),
        CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_goal_milestones_completed_at_status",
        ),
    )

    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    target_date: Mapped[date | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(
        String(16), default="NOT_STARTED", server_default="NOT_STARTED",
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class GoalCheckpoint(GoalCompositionFields, Base):
    __tablename__ = "goal_checkpoints"
    __table_args__ = (
        *_parent_constraints("goal_checkpoints"),
        _money_constraint("goal_checkpoints", "amount_cents", optional=False),
    )

    amount_cents: Mapped[int] = mapped_column(BigInteger)
    label: Mapped[str | None] = mapped_column(String(100))
    # Reached is intentionally absent: every read must compare current meaningful
    # manual Goal progress with amount_cents, without saving derived state.


for _model in (GoalItem, GoalMilestone, GoalCheckpoint):
    register_sqlite_goal_guards(_model.__table__)