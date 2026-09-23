"""Immutable snapshots of transaction edits and deletions."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, JSON, String
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class TransactionCorrection(Base):
    __tablename__ = "transaction_corrections"
    __table_args__ = (
        Index("ix_transaction_corrections_account_changed", "account_id", "changed_at"),
        Index("ix_transaction_corrections_owner_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    transaction_id: Mapped[int] = mapped_column(ForeignKey("transactions.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(10), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    before: Mapped[dict] = mapped_column(JSON, nullable=False)
    after: Mapped[dict | None] = mapped_column(JSON)