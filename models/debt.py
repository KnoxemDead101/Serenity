"""
Debt database model.

A Debt is a liability: credit cards, loans, medical debt. Credit cards
live here, never as Accounts, so the same money owed is counted once.

`interest_rate_milli` stores thousandths of a percent so rates like
6.875% are exact (6.875% -> 6875). See utils/money.py.
"""

from datetime import date, datetime

from sqlalchemy import Boolean, Date, DateTime, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Debt(Base):
    __tablename__ = "debts"
    __table_args__ = (Index("ix_debts_owner_id", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    debt_type: Mapped[str] = mapped_column(String(50), default="Other")
    balance_cents: Mapped[int] = mapped_column(Integer, default=0)
    interest_rate_milli: Mapped[int] = mapped_column(Integer, default=0)
    minimum_payment_cents: Mapped[int] = mapped_column(Integer, default=0)
    due_date: Mapped[date | None] = mapped_column(Date)
    notes: Mapped[str | None] = mapped_column(Text)
    # False = deactivated. Keep inactive records for history, but exclude them
    # from debt totals. Records are never hard-deleted.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )