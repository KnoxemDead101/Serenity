"""Owner-private reference instruments and immutable versioned specifications.

Neither reference instruments nor calculator results are financial assets or
executed trades. Existing Investment records and net-worth math are separate.
"""

from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column, relationship

from models.account import utc_now
from services.ownership import OWNER_ID_MAX_LENGTH
from storage.database import Base


class Instrument(Base):
    __tablename__ = "instruments"
    __table_args__ = (
        UniqueConstraint("owner_id", "symbol", name="uq_instruments_owner_symbol"),
        Index("ix_instruments_owner_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    # Normalized to uppercase, and never edited after creation.
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true(), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, onupdate=utc_now, nullable=False
    )
    specifications: Mapped[list["InstrumentSpecification"]] = relationship(
        back_populates="instrument", lazy="selectin", order_by="InstrumentSpecification.version"
    )


class InstrumentSpecification(Base):
    __tablename__ = "instrument_specifications"
    __table_args__ = (
        UniqueConstraint("instrument_id", "version", name="uq_instrument_specifications_version"),
        Index("ix_instrument_specifications_owner_id", "owner_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    instrument_id: Mapped[int] = mapped_column(
        ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False
    )
    owner_id: Mapped[str] = mapped_column(String(OWNER_ID_MAX_LENGTH), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    symbol: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    asset_type: Mapped[str] = mapped_column(String(10), nullable=False)
    exchange: Mapped[str | None] = mapped_column(String(100))
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    # Prices and point values are exact decimal values stored at 1e-8 scale.
    tick_size_units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    point_value_units: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, nullable=False)
    instrument: Mapped[Instrument] = relationship(back_populates="specifications")