"""Dependent labels for transactions; dependents are soft-deactivated."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint, text, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Dependent(Base):
    __tablename__ = "dependents"
    __table_args__ = (
        UniqueConstraint("owner_id", "display_name", name="uq_dependents_owner_name"),
        Index(
            "uq_dependents_owner_name_lower",
            "owner_id",
            text("lower(display_name)"),
            unique=True,
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )