"""Latest owner assertion for a specific financial snapshot, not an audit."""

from datetime import date, datetime

from sqlalchemy import CheckConstraint, Date, DateTime, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Verification(Base):
    __tablename__ = "manual_verifications"
    __table_args__ = (
        UniqueConstraint("owner_id", "kind", "target_id", name="uq_manual_verifications_target"),
        CheckConstraint(
            "kind IN ('account_balance', 'debt_balance', 'legacy_valuation', 'opening_valuation')",
            name="ck_manual_verifications_kind",
        ),
        CheckConstraint("target_id > 0", name="ck_manual_verifications_target"),
        CheckConstraint("length(trim(evidence)) BETWEEN 1 AND 1000", name="ck_manual_verifications_evidence"),
        CheckConstraint("length(snapshot) = 64", name="ck_manual_verifications_snapshot"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    target_id: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[str] = mapped_column(String(64), nullable=False)
    as_of: Mapped[date] = mapped_column(Date, nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    recorded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)