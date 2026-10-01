"""
Investment database model (TEMPORARY starting-position model).

This stores what you own today: quantity, what you paid (cost basis) and
what it's worth now. The Portfolio milestone will replace it with
Portfolio -> Holdings -> Investment Transactions, where cost basis is
calculated from purchase history instead of typed in.

`quantity_units` stores quantity in units of 0.00000001 so fractional
shares are exact (0.5 shares -> 50,000,000). See utils/money.py.

PostgreSQL INTEGER overflows after about 21.47 shares at this precision.
BIGINT supports the quantity bound validated by schemas/finance.py.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, Index, Integer, String, Text, false, true
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
    quantity_units: Mapped[int] = mapped_column(BigInteger, default=0)
    cost_basis_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    current_value_cents: Mapped[int] = mapped_column(BigInteger, default=0)
    notes: Mapped[str | None] = mapped_column(Text)
    # A newly assigned investment is an uncounted candidate until reviewed.
    # Legacy rows default to counted and remain unchanged by the migration.
    investment_account_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Direct portfolio membership does not imply a cash-account link.
    portfolio_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    review_pending: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default=false())
    # False = deactivated via the legacy lifecycle endpoint; excluded from totals.
    # The Delete action permanently removes either active or inactive records.
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )