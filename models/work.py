"""Owner-private work tracking, deliberately separate from financial planning."""

from datetime import date, datetime

from sqlalchemy import (
    Boolean, CheckConstraint, Date, DateTime, ForeignKeyConstraint, Index,
    Integer, String, Text, UniqueConstraint, true,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from models.work_sqlite import register_work_guards
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base

WORK_STATUSES = ["NOT_STARTED", "IN_PROGRESS", "COMPLETED", "PAUSED", "CANCELLED"]
WORK_PRIORITIES = ["HIGH", "NORMAL", "LOW"]


def work_constraints(table: str) -> tuple:
    """Status and completion time must agree even for direct database writes."""
    return (
        Index(f"ix_{table}_owner_id", "owner_id"),
        CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'PAUSED', 'CANCELLED')",
            name=f"ck_{table}_status",
        ),
        CheckConstraint("priority IN ('HIGH', 'NORMAL', 'LOW')", name=f"ck_{table}_priority"),
        CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name=f"ck_{table}_completed_at_status",
        ),
    )


class WorkFields:
    """Actionable work has no money, transaction, or progress columns."""

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    notes: Mapped[str | None] = mapped_column(Text)
    priority: Mapped[str] = mapped_column(String(8), default="NORMAL", server_default="NORMAL")
    status: Mapped[str] = mapped_column(
        String(16), default="NOT_STARTED", server_default="NOT_STARTED",
    )
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now,
    )


class Project(WorkFields, Base):
    __tablename__ = "projects"
    __table_args__ = (
        *work_constraints("projects"),
        UniqueConstraint("owner_id", "id", name="uq_projects_owner_id_id"),
        ForeignKeyConstraint(
            ["owner_id", "goal_id"], ["goals.owner_id", "goals.id"],
            name="fk_projects_owner_goal", ondelete="RESTRICT",
        ),
        Index("ix_projects_goal_id", "goal_id"),
    )

    goal_id: Mapped[int | None] = mapped_column(Integer)
    target_date: Mapped[date | None] = mapped_column(Date)


class Task(WorkFields, Base):
    __tablename__ = "tasks"
    __table_args__ = (
        *work_constraints("tasks"),
        ForeignKeyConstraint(
            ["owner_id", "project_id"], ["projects.owner_id", "projects.id"],
            name="fk_tasks_owner_project", ondelete="RESTRICT",
        ),
        Index("ix_tasks_project_id", "project_id"),
    )

    project_id: Mapped[int | None] = mapped_column(Integer)
    due_date: Mapped[date | None] = mapped_column(Date)


register_work_guards(Project.__table__, "goals", "goal_id")
register_work_guards(Task.__table__, "projects", "project_id")