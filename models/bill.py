"""
Bill database model.

A Bill is an EXPECTED obligation (rent, insurance, a subscription).
It is not proof that money moved; that is a Transaction. Keeping them
separate prevents counting the same spending twice.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Bill(Base):
    __tablename__ = "bills"
    __table_args__ = (Index("ix_bills_owner_id", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    amount_cents: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[date] = mapped_column(Date)
    # Monthly, Quarterly, Annual or One-time (see utils/choices.py).
    frequency: Mapped[str] = mapped_column(String(30), default="Monthly")
    category: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)
    # False = deactivated. Keep inactive records for history, but exclude them
    # from recurring totals. Records are never hard-deleted.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )