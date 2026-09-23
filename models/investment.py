"""
Investment database model (TEMPORARY starting-position model).

This stores what you own today: quantity, what you paid (cost basis) and
what it's worth now. The Portfolio milestone will replace it with
Portfolio -> Holdings -> Investment Transactions, where cost basis is
calculated from purchase history instead of typed in.

`quantity_units` stores quantity in units of 0.00000001 so fractional
shares are exact (0.5 shares -> 50,000,000). See utils/money.py.
"""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Investment(Base):
    __tablename__ = "investments"
    __table_args__ = (Index("ix_investments_owner_id", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100))
    ticker: Mapped[str | None] = mapped_column(String(20))
    quantity_units: Mapped[int] = mapped_column(Integer, default=0)
    cost_basis_cents: Mapped[int] = mapped_column(Integer, default=0)
    current_value_cents: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    # False = deactivated. Keep inactive records for history, but exclude them
    # from investment totals. Records are never hard-deleted.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )