"""Operational evidence only; financial Data Health is deliberately excluded."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


class SystemObservation(Base):
    __tablename__ = "system_observations"
    __table_args__ = (
        Index("ix_system_observations_owner_id_id", "owner_id", "id"),
        Index("ix_system_observations_checked_at", "checked_at"),
        CheckConstraint("kind IN ('BASELINE', 'TRANSITION')", name="ck_system_observations_kind"),
        CheckConstraint("state IN ('NORMAL', 'READ_ONLY', 'UNAVAILABLE')", name="ck_system_observations_state"),
        CheckConstraint("database IN ('AVAILABLE', 'UNAVAILABLE')", name="ck_system_observations_database"),
        CheckConstraint("schema IN ('AVAILABLE', 'UNAVAILABLE')", name="ck_system_observations_schema"),
        CheckConstraint("write_safety IN ('AVAILABLE', 'READ_ONLY', 'UNAVAILABLE')", name="ck_system_observations_write_safety"),
        CheckConstraint("migration IN ('CURRENT', 'BEHIND', 'UNVERIFIED')", name="ck_system_observations_migration"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("workspaces.id", name="fk_system_observations_workspace", ondelete="CASCADE"),
        nullable=False,
    )
    checked_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    state: Mapped[str] = mapped_column(String(11), nullable=False)
    database: Mapped[str] = mapped_column(String(11), nullable=False)
    schema: Mapped[str] = mapped_column(String(11), nullable=False)
    write_safety: Mapped[str] = mapped_column(String(11), nullable=False)
    migration: Mapped[str] = mapped_column(String(10), nullable=False)