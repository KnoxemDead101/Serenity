"""Separate Serenity workspaces from provider user IDs.

Populated legacy databases require an explicitly verified single-issuer
provenance. Mixed-provider histories need a separately audited mapping.
"""

import base64
import os
import re
import uuid
from datetime import datetime, timezone
from urllib.parse import urlsplit

from alembic import op
import sqlalchemy as sa

revision = "0011_identity_and_workspaces"
down_revision = "0010_income_profiles"
branch_labels = None
depends_on = None

FINANCIAL_TABLES = (
    "accounts", "bills", "debts", "investments", "businesses", "dependents",
    "transactions", "transaction_corrections", "income_profiles",
)


def _configured_issuer():
    key = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    if not key.startswith(("pk_test_", "pk_live_")):
        raise RuntimeError("A valid configured Clerk publishable key is required")
    try:
        host = base64.b64decode(
            key.split("_", 2)[2] + "=" * (-len(key.split("_", 2)[2]) % 4),
            validate=True,
        ).decode()
    except (ValueError, UnicodeDecodeError) as exc:
        raise RuntimeError("Invalid Clerk publishable key") from exc
    if not host.endswith("$") or not re.fullmatch(
        r"[a-zA-Z0-9]+(?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host[:-1]
    ):
        raise RuntimeError("Invalid Clerk publishable key host")
    return "https://" + host[:-1]


def _owners(connection):
    owners = set()
    for table in FINANCIAL_TABLES:
        rows = connection.execute(sa.text(f"SELECT DISTINCT owner_id FROM {table}"))
        for (owner,) in rows:
            if not owner or not re.fullmatch(r"[A-Za-z0-9_-]{1,255}", owner):
                raise RuntimeError(f"Invalid legacy owner in {table}; manual migration required")
            owners.add(owner)
    return owners


def _legacy_issuer(connection):
    owners = _owners(connection)
    if not owners:
        return owners, None
    issuer = os.getenv("SERENITY_LEGACY_CLERK_ISSUER", "").strip()
    parsed = urlsplit(issuer)
    if not issuer or parsed.scheme != "https" or not parsed.hostname or parsed.username \
            or parsed.password or parsed.path or parsed.query or parsed.fragment \
            or parsed.port or issuer != _configured_issuer():
        raise RuntimeError(
            "Populated legacy owners require SERENITY_LEGACY_CLERK_ISSUER "
            "equal to the configured Clerk issuer; confirm every owner belongs "
            "to that tenant or use an audited per-owner migration"
        )
    return owners, issuer


def upgrade():
    connection = op.get_bind()
    # Especially on SQLite, abort BEFORE DDL; SQLite DDL may autocommit.
    owners, issuer = _legacy_issuer(connection)
    op.create_table(
        "users", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "workspaces", sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("owner_user_id", sa.String(36),
                  sa.ForeignKey("users.id", name="fk_workspaces_owner_user_id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_user_id", name="uq_workspaces_owner_user_id"),
    )
    op.create_table(
        "auth_identities", sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.String(36),
                  sa.ForeignKey("users.id", name="fk_auth_identities_user_id"), nullable=False),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("issuer", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_sign_in_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("provider", "issuer", "subject",
                            name="uq_auth_identities_provider_issuer_subject"),
    )
    op.create_index("ix_auth_identities_user_id", "auth_identities", ["user_id"])
    now = datetime.now(timezone.utc)
    for old_owner in sorted(owners):
        user_id, workspace_id = str(uuid.uuid4()), str(uuid.uuid4())
        connection.execute(sa.text(
            "INSERT INTO users (id, active, created_at) VALUES (:id, true, :now)"
        ), {"id": user_id, "now": now})
        connection.execute(sa.text(
            "INSERT INTO workspaces (id, owner_user_id, name, created_at) "
            "VALUES (:id, :user_id, 'Primary', :now)"
        ), {"id": workspace_id, "user_id": user_id, "now": now})
        connection.execute(sa.text(
            "INSERT INTO auth_identities (user_id, provider, issuer, subject, created_at) "
            "VALUES (:user_id, 'clerk', :issuer, :subject, :now)"
        ), {"user_id": user_id, "issuer": issuer, "subject": old_owner, "now": now})
        for table in FINANCIAL_TABLES:
            connection.execute(sa.text(
                f"UPDATE {table} SET owner_id = :new WHERE owner_id = :old"
            ), {"new": workspace_id, "old": old_owner})


def downgrade():
    connection = op.get_bind()
    identities = connection.execute(sa.text(
        "SELECT w.id, i.provider, i.issuer, i.subject FROM workspaces w "
        "LEFT JOIN auth_identities i ON i.user_id = w.owner_user_id"
    )).all()
    # Never guess an identity if a workspace has multiple identities; and
    # never drop identities that have no workspace or any financial owner orphan.
    identity_count = connection.scalar(sa.text("SELECT COUNT(*) FROM auth_identities"))
    user_count = connection.scalar(sa.text("SELECT COUNT(*) FROM users"))
    mappings = {}
    subjects = set()
    for ws, provider, issuer, subject in identities:
        if ws in mappings or not subject or provider != "clerk" or (issuer, subject) in subjects:
            raise RuntimeError("Ambiguous identity mapping; restore from backup")
        mappings[ws] = subject
        subjects.add((issuer, subject))
    if identity_count != len(mappings) or user_count != len(mappings):
        raise RuntimeError("Orphan identity or user; restore from backup")
    financial_count = 0
    for table in FINANCIAL_TABLES:
        for owner, count in connection.execute(
            sa.text(f"SELECT owner_id, COUNT(*) FROM {table} GROUP BY owner_id")
        ):
            if owner not in mappings:
                raise RuntimeError("Unmapped financial owner; restore from backup")
            financial_count += count
    if (mappings or financial_count) and os.getenv("SERENITY_CONFIRM_WORKSPACE_DOWNGRADE") != "1":
        raise RuntimeError("Populated downgrade requires explicit backup and confirmation")
    if financial_count:
        expected = _configured_issuer()
        if any(issuer != expected for _, _, issuer, _ in identities):
            raise RuntimeError("Different identity issuers; restore from backup")
    for workspace, subject in mappings.items():
        for table in FINANCIAL_TABLES:
            connection.execute(sa.text(
                f"UPDATE {table} SET owner_id = :subject WHERE owner_id = :ws"
            ), {"subject": subject, "ws": workspace})
    op.drop_index("ix_auth_identities_user_id", table_name="auth_identities")
    op.drop_table("auth_identities")
    op.drop_table("workspaces")
    op.drop_table("users")