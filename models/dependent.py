"""Dependent labels for transactions; dependents are soft-deactivated."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, text, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from storage.database import Base


class Dependent(Base):
    __tablename__ = "dependents"
    __table_args__ = (
        UniqueConstraint("display_name", name="uq_dependents_display_name"),
        Index("uq_dependents_display_name_lower", text("lower(display_name)"), unique=True),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )