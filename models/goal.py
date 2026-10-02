"""Private, standalone goals; no financial activity or related goal records yet.

Amounts are optional integer cents. A goal never changes an account balance,
debt, investment, or net worth. Reserved progress sources are metadata only.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger, Boolean, CheckConstraint, Date, DateTime, Index, Integer,
    String, Text, UniqueConstraint, true,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base
from utils.choices import (
    GOAL_CATEGORIES, GOAL_PRIORITIES, GOAL_PROGRESS_SOURCES, GOAL_STATUSES, GOAL_TYPES,
)


def _choice_constraint(column: str, choices: list[str]) -> CheckConstraint:
    """Use the same fixed choices at the API and persistence boundaries."""
    values = ", ".join(f"'{value}'" for value in choices)
    return CheckConstraint(f"{column} IN ({values})", name=f"ck_goals_{column}")


class Goal(Base):
    __tablename__ = "goals"
    __table_args__ = (
        Index("ix_goals_owner_id", "owner_id"),
        # Reserved for future owner-matched child foreign keys; none exist yet.
        UniqueConstraint("owner_id", "id", name="uq_goals_owner_id_id"),
        _choice_constraint("goal_type", GOAL_TYPES),
        _choice_constraint("category", GOAL_CATEGORIES),
        _choice_constraint("status", GOAL_STATUSES),
        _choice_constraint("priority", GOAL_PRIORITIES),
        _choice_constraint("progress_source", GOAL_PROGRESS_SOURCES),
        CheckConstraint(
            "target_amount_cents IS NULL OR "
            "target_amount_cents BETWEEN 0 AND 100000000000000",
            name="ck_goals_target_amount_cents",
        ),
        CheckConstraint(
            "current_progress_amount_cents IS NULL OR "
            "current_progress_amount_cents BETWEEN 0 AND 100000000000000",
            name="ck_goals_current_progress_amount_cents",
        ),
        CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_goals_completed_at_status",
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    description: Mapped[str | None] = mapped_column(Text)
    goal_type: Mapped[str] = mapped_column(String(32))
    category: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(
        String(16), default="NOT_STARTED", server_default="NOT_STARTED",
    )
    priority: Mapped[str] = mapped_column(
        String(8), default="NORMAL", server_default="NORMAL",
    )
    target_date: Mapped[date | None] = mapped_column(Date)
    target_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    progress_source: Mapped[str] = mapped_column(
        String(32), default="MANUAL", server_default="MANUAL",
    )
    # Only holds real progress when progress_source is MANUAL. Future automatic
    # sources must calculate progress, never read or trust this stored field.
    current_progress_amount_cents: Mapped[int | None] = mapped_column(BigInteger)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now,
    )