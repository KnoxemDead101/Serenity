"""Durable, owner-scoped records for reviewed investment conversions.

These tables are an audit ledger only. Creating them does not convert or
otherwise alter existing investments, account balances, or valuations.
"""

from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from models.instrument import Instrument, InstrumentSpecification
from models.investment import Investment
from models.portfolio import InvestmentAccount
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base

# Publish must carry these keys before creating their dependent foreign keys.
# Model them as real constraints, not only standalone unique indexes.
UniqueConstraint(
    Investment.__table__.c.owner_id, Investment.__table__.c.id,
    name="uq_investments_owner_id_id",
)
UniqueConstraint(
    InvestmentAccount.__table__.c.owner_id,
    InvestmentAccount.__table__.c.id,
    name="uq_investment_accounts_owner_id_id",
)
UniqueConstraint(
    Instrument.__table__.c.owner_id, Instrument.__table__.c.id,
    name="uq_instruments_owner_id_id",
)
UniqueConstraint(
    InstrumentSpecification.__table__.c.owner_id,
    InstrumentSpecification.__table__.c.instrument_id,
    InstrumentSpecification.__table__.c.id,
    name="uq_instrument_specifications_owner_id_instrument_id_id",
)


class ReconciliationApproval(Base):
    __tablename__ = "reconciliation_approvals"
    __table_args__ = (
        UniqueConstraint("owner_id", "id", name="uq_reconciliation_approvals_owner_id_id"),
        UniqueConstraint("owner_id", "report_sha256", name="uq_reconciliation_approvals_owner_digest"),
        CheckConstraint(
            "state IN ('approved', 'executed', 'reversed', 'expired')",
            name="ck_reconciliation_approvals_state",
        ),
        CheckConstraint(
            "(execution_idempotency_key IS NULL AND execution_payload_sha256 IS NULL) OR "
            "(execution_idempotency_key IS NOT NULL AND execution_payload_sha256 IS NOT NULL)",
            name="ck_reconciliation_approvals_execution_binding",
        ),
        UniqueConstraint(
            "owner_id", "execution_idempotency_key",
            name="uq_reconciliation_approvals_owner_idempotency_key",
        ),
        Index("ix_reconciliation_approvals_owner_state", "owner_id", "state"),
        Index("ix_reconciliation_approvals_owner_approved_at", "owner_id", "approved_at"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    canonical_report: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    report_format_version: Mapped[int] = mapped_column(Integer, nullable=False)
    algorithm_version: Mapped[str] = mapped_column(String(100), nullable=False)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    signed_token_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    preview_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_fingerprint: Mapped[str] = mapped_column(Text, nullable=False)
    approving_actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    approved_source_ids: Mapped[str] = mapped_column(Text, nullable=False)
    account_corrections_cents: Mapped[str] = mapped_column(Text, nullable=False)
    before_component_totals_cents: Mapped[str] = mapped_column(Text, nullable=False)
    after_component_totals_cents: Mapped[str] = mapped_column(Text, nullable=False)
    expected_delta_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    backup_evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    backup_cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    rollback_deadline: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    state: Mapped[str] = mapped_column(String(10), nullable=False, default="approved")
    execution_idempotency_key: Mapped[str | None] = mapped_column(String(255))
    execution_payload_sha256: Mapped[str | None] = mapped_column(String(64))
    executed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    reversed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class OpeningPosition(Base):
    __tablename__ = "opening_positions"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "approval_id"],
            ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_opening_positions_owner_approval",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_investment_id"],
            ["investments.owner_id", "investments.id"],
            name="fk_opening_positions_owner_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "portfolio_id"],
            ["portfolios.owner_id", "portfolios.id"],
            name="fk_opening_positions_owner_portfolio",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "investment_account_id"],
            ["investment_accounts.owner_id", "investment_accounts.id"],
            name="fk_opening_positions_owner_container",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "cash_account_id"],
            ["accounts.owner_id", "accounts.id"],
            name="fk_opening_positions_owner_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "instrument_id"],
            ["instruments.owner_id", "instruments.id"],
            name="fk_opening_positions_owner_instrument",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "instrument_id", "specification_id"],
            [
                "instrument_specifications.owner_id",
                "instrument_specifications.instrument_id",
                "instrument_specifications.id",
            ],
            name="fk_opening_positions_owner_specification",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("owner_id", "source_investment_id", name="uq_opening_positions_owner_source"),
        UniqueConstraint("owner_id", "id", name="uq_opening_positions_owner_id_id"),
        UniqueConstraint(
            "owner_id", "source_investment_id", "id", "approval_id",
            name="uq_opening_positions_owner_source_id_approval",
        ),
        CheckConstraint("quantity_units >= 0", name="ck_opening_positions_quantity_nonnegative"),
        CheckConstraint("basis_status IN ('known', 'unknown', 'unverified')", name="ck_opening_positions_basis_status"),
        CheckConstraint("status IN ('active', 'reversed')", name="ck_opening_positions_status"),
        Index("ix_opening_positions_owner_approval", "owner_id", "approval_id"),
        Index("ix_opening_positions_owner_status", "owner_id", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    approval_id: Mapped[int] = mapped_column(Integer, nullable=False)
    source_investment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    portfolio_id: Mapped[int | None] = mapped_column(Integer)
    investment_account_id: Mapped[int | None] = mapped_column(Integer)
    cash_account_id: Mapped[int | None] = mapped_column(Integer)
    instrument_id: Mapped[int] = mapped_column(Integer, nullable=False)
    specification_id: Mapped[int] = mapped_column(Integer, nullable=False)
    specification_version: Mapped[int] = mapped_column(Integer, nullable=False)
    quantity_units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    entered_basis_cents: Mapped[int | None] = mapped_column(BigInteger)
    basis_status: Mapped[str] = mapped_column(String(10), nullable=False)
    reviewed_zero_basis_evidence: Mapped[str | None] = mapped_column(Text)
    original_entered_value_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    valuation_provenance: Mapped[str | None] = mapped_column(String(20))
    valuation_evidence: Mapped[str | None] = mapped_column(Text)
    valuation_as_of_date: Mapped[date | None] = mapped_column(Date)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    source_edited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acquisition_date: Mapped[date | None] = mapped_column(Date)
    source_snapshot: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="active")


class ValuationEligibility(Base):
    """Current valuation selection; conversion_events retain each transition."""

    __tablename__ = "valuation_eligibility"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "source_investment_id"],
            ["investments.owner_id", "investments.id"],
            name="fk_valuation_eligibility_owner_source",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "opening_position_id"],
            ["opening_positions.owner_id", "opening_positions.id"],
            name="fk_valuation_eligibility_owner_opening",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "approval_id"],
            ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_valuation_eligibility_owner_approval",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "source_investment_id", "opening_position_id", "approval_id"],
            [
                "opening_positions.owner_id",
                "opening_positions.source_investment_id",
                "opening_positions.id",
                "opening_positions.approval_id",
            ],
            name="fk_valuation_eligibility_exact_opening",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("owner_id", "source_investment_id", name="uq_valuation_eligibility_owner_source"),
        UniqueConstraint("owner_id", "opening_position_id", name="uq_valuation_eligibility_owner_opening"),
        CheckConstraint("representation IN ('legacy', 'opening')", name="ck_valuation_eligibility_representation"),
        CheckConstraint("status IN ('active', 'reversed')", name="ck_valuation_eligibility_status"),
        CheckConstraint(
            "(status = 'active' AND representation = 'opening') OR "
            "(status = 'reversed' AND representation = 'legacy')",
            name="ck_valuation_eligibility_selected_representation",
        ),
        Index("ix_valuation_eligibility_owner_representation", "owner_id", "representation", "status"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    source_investment_id: Mapped[int] = mapped_column(Integer, nullable=False)
    opening_position_id: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_id: Mapped[int] = mapped_column(Integer, nullable=False)
    representation: Mapped[str] = mapped_column(String(7), nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="active")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False)


class CashReconciliationEntry(Base):
    __tablename__ = "cash_reconciliation_entries"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "approval_id"],
            ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_cash_reconciliation_entries_owner_approval",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "account_id"],
            ["accounts.owner_id", "accounts.id"],
            name="fk_cash_reconciliation_entries_owner_account",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["owner_id", "original_entry_id"],
            ["cash_reconciliation_entries.owner_id", "cash_reconciliation_entries.id"],
            name="fk_cash_reconciliation_entries_owner_original",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "approval_id", "account_id", "reason",
            name="uq_cash_reconciliation_entries_approval_account_reason",
        ),
        UniqueConstraint("owner_id", "id", name="uq_cash_reconciliation_entries_owner_id_id"),
        CheckConstraint(
            "reason IN ('combined_balance_overlap', 'conversion_reversal')",
            name="ck_cash_reconciliation_entries_reason",
        ),
        CheckConstraint(
            "(reason = 'combined_balance_overlap' AND original_entry_id IS NULL) OR "
            "(reason = 'conversion_reversal' AND original_entry_id IS NOT NULL)",
            name="ck_cash_reconciliation_entries_reversal_link",
        ),
        Index("ix_cash_reconciliation_entries_owner_account", "owner_id", "account_id"),
        Index("ix_cash_reconciliation_entries_owner_approval", "owner_id", "approval_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    approval_id: Mapped[int] = mapped_column(Integer, nullable=False)
    account_id: Mapped[int] = mapped_column(Integer, nullable=False)
    delta_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    reason: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    before_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    after_balance_cents: Mapped[int] = mapped_column(BigInteger, nullable=False)
    original_entry_id: Mapped[int | None] = mapped_column(Integer)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)


class ConversionEvent(Base):
    __tablename__ = "conversion_events"
    __table_args__ = (
        ForeignKeyConstraint(
            ["owner_id", "approval_id"],
            ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_conversion_events_owner_approval",
            ondelete="RESTRICT",
        ),
        UniqueConstraint("owner_id", "id", name="uq_conversion_events_owner_id_id"),
        CheckConstraint(
            "event_kind IN ('executed', 'reversed', 'failed')",
            name="ck_conversion_events_kind",
        ),
        Index("ix_conversion_events_owner_approval", "owner_id", "approval_id"),
        Index("ix_conversion_events_owner_created_at", "owner_id", "created_at"),
        Index(
            "uq_conversion_events_owner_approval_executed",
            "owner_id",
            "approval_id",
            unique=True,
            sqlite_where=text("event_kind = 'executed'"),
            postgresql_where=text("event_kind = 'executed'"),
        ),
        Index(
            "uq_conversion_events_owner_approval_reversed",
            "owner_id",
            "approval_id",
            unique=True,
            sqlite_where=text("event_kind = 'reversed'"),
            postgresql_where=text("event_kind = 'reversed'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    approval_id: Mapped[int] = mapped_column(Integer, nullable=False)
    event_kind: Mapped[str] = mapped_column(String(8), nullable=False)
    before_totals: Mapped[str] = mapped_column(Text, nullable=False)
    after_totals: Mapped[str] = mapped_column(Text, nullable=False)
    source_account_state: Mapped[str] = mapped_column(Text, nullable=False)
    cutoff: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    report_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    backup_evidence_reference: Mapped[str] = mapped_column(Text, nullable=False)
    linked_ids: Mapped[str] = mapped_column(Text, nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)