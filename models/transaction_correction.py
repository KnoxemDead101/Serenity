"""Immutable snapshots of transaction edits and deletions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from storage.database import Base


class TransactionCorrection(Base):
    __tablename__ = "transaction_corrections"
    __table_args__ = (
        Index("ix_transaction_corrections_account_changed", "account_id", "changed_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    before: Mapped[dict] = mapped_column(JSON, nullable=False)
    after: Mapped[dict | None] = mapped_column(JSON)