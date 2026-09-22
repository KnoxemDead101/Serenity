"""
Account database model.

An Account is a modeled financial account: checking, savings, a
brokerage account, a credit card, and so on. Serenity does not connect
to real banks; the user describes their accounts here.

This class describes the "accounts" TABLE: one attribute per column.

A NOTE ON BALANCES
------------------
We store `opening_balance_cents`, the balance when the user started
tracking the account in Serenity. We do NOT store a current balance.
Once transactions exist (next slice), the current balance will be:

    current balance = opening balance + money in - money out

It is calculated in services/account_service.py. Storing it separately
would mean two numbers that could disagree.
"""

from datetime import datetime, timezone

from sqlalchemy import Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from storage.database import Base


def utc_now() -> datetime:
    """Current time in UTC. Storing UTC avoids time-zone confusion."""
    return datetime.now(timezone.utc)


class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    account_type: Mapped[str] = mapped_column(String(50))
    classification: Mapped[str] = mapped_column(String(50))

    # Stored in cents. See utils/money.py for why.
    opening_balance_cents: Mapped[int] = mapped_column(Integer, default=0)

    # "str | None" means the column may be empty (NULL).
    institution: Mapped[str | None] = mapped_column(String(100))
    notes: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(default=utc_now, onupdate=utc_now)

    def __repr__(self) -> str:
        return f"Account(id={self.id}, name={self.name!r}, type={self.account_type!r})"
