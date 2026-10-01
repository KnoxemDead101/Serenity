"""Private organizational containers; neither model owns a financial balance."""

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKeyConstraint, Index, Integer, String, Text, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Portfolio(Base):
    __tablename__ = "portfolios"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_portfolios_owner_id_id"),
        Index("ix_portfolios_owner_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)


class InvestmentAccount(Base):
    __tablename__ = "investment_accounts"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "portfolio_id"], ["portfolios.owner_id", "portfolios.id"],
            name="fk_investment_accounts_owner_portfolio", ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "account_id"], ["accounts.owner_id", "accounts.id"],
            name="fk_investment_accounts_owner_account", ondelete="RESTRICT",
        ),
        UniqueConstraint("account_id", name="uq_investment_accounts_account_id"),
        Index("ix_investment_accounts_owner_id", "owner_id"),
        Index("ix_investment_accounts_owner_portfolio", "owner_id", "portfolio_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    portfolio_id: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utc_now, onupdate=utc_now)