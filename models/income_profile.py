"""Stored expectations about how a user receives income (not transactions)."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class IncomeProfile(Base):
    __tablename__ = "income_profiles"
    __table_args__ = (Index("ix_income_profiles_owner_id", "owner_id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    income_type: Mapped[str] = mapped_column(String(20), nullable=False)
    classification: Mapped[str] = mapped_column(
        String(20), nullable=False, default="Personal"
    )
    pay_frequency: Mapped[str | None] = mapped_column(String(20))

    hourly_rate_cents: Mapped[int | None] = mapped_column(Integer)
    standard_hours_hundredths: Mapped[int | None] = mapped_column(Integer)
    expected_hours_hundredths: Mapped[int | None] = mapped_column(Integer)
    annual_salary_cents: Mapped[int | None] = mapped_column(Integer)
    amount_per_period_cents: Mapped[int | None] = mapped_column(Integer)
    expected_net_per_period_cents: Mapped[int | None] = mapped_column(Integer)

    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )