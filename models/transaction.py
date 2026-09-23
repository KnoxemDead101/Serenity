"""
Transaction database model.

A Transaction is financially meaningful money entering or leaving ONE
account (v0.2 handoff, section 8).

Rules that keep the numbers trustworthy:
- `amount_cents` is always positive. `transaction_type` (Income/Expense)
  says which direction the money moved.
- Transactions are never physically deleted. Deleting sets `deleted_at`,
  and every edit/delete is recorded in `transaction_corrections`.
- `classification` is stored on the transaction itself, because one
  account can hold activity of different kinds (e.g. a business expense
  paid from a personal account). When the user doesn't pick one, the
  service copies the account's classification.
- All timestamps are time-zone-aware UTC (see migration 0005).
"""

from datetime import date, datetime

from sqlalchemy import Date, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.account import Account, utc_now
from models.business import Business
from models.dependent import Dependent
from storage.database import Base


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (Index("ix_transactions_account_date", "account_id", "date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    transaction_type: Mapped[str] = mapped_column(String(20), nullable=False)
    classification: Mapped[str] = mapped_column(String(50), nullable=False)
    amount_cents: Mapped[int] = mapped_column(Integer, nullable=False)

    # The reason money moved (required) and optional details about where.
    description: Mapped[str] = mapped_column(String(200), nullable=False)
    merchant: Mapped[str | None] = mapped_column(String(100))
    location: Mapped[str | None] = mapped_column(String(100))
    category: Mapped[str | None] = mapped_column(String(100))
    subcategory: Mapped[str | None] = mapped_column(String(100))
    business_id: Mapped[int | None] = mapped_column(
        ForeignKey("businesses.id", name="fk_transactions_business_id")
    )
    dependent_id: Mapped[int | None] = mapped_column(
        ForeignKey("dependents.id", name="fk_transactions_dependent_id")
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    account: Mapped[Account] = relationship(back_populates="transactions")
    business: Mapped[Business | None] = relationship()
    dependent: Mapped[Dependent | None] = relationship()