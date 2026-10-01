"""Internal account ownership is separate from external authentication."""

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, true
from sqlalchemy.orm import Mapped, mapped_column

from models.account import utc_now
from storage.database import Base

UUID_LENGTH = 36
PROVIDER_MAX_LENGTH = 50
EXTERNAL_ID_MAX_LENGTH = 255


def new_uuid() -> str:
    return str(uuid.uuid4())


class SerenityUser(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True, default=new_uuid)
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default=true())
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class Workspace(Base):
    __tablename__ = "workspaces"
    __table_args__ = (UniqueConstraint("owner_user_id", name="uq_workspaces_owner_user_id"),)

    id: Mapped[str] = mapped_column(String(UUID_LENGTH), primary_key=True, default=new_uuid)
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="fk_workspaces_owner_user_id"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False, default="Primary")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class AuthIdentity(Base):
    __tablename__ = "auth_identities"
    __table_args__ = (
        UniqueConstraint("provider", "issuer", "subject",
                         name="uq_auth_identities_provider_issuer_subject"),
        Index("ix_auth_identities_user_id", "user_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", name="fk_auth_identities_user_id"), nullable=False
    )
    provider: Mapped[str] = mapped_column(String(PROVIDER_MAX_LENGTH), nullable=False)
    issuer: Mapped[str] = mapped_column(String(EXTERNAL_ID_MAX_LENGTH), nullable=False)
    subject: Mapped[str] = mapped_column(String(EXTERNAL_ID_MAX_LENGTH), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    last_sign_in_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))