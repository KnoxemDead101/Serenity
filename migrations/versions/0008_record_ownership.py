"""Scope financial records to their authenticated Serenity owner.

Existing rows are deliberately assigned to one operator-provided owner.  A
populated database must set SERENITY_LEGACY_OWNER_ID before this migration so
an invited member is never granted an arbitrary person's data.
"""

import os
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0008_record_ownership"
down_revision: Union[str, None] = "0007_business_and_dependents"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = (
    "accounts",
    "bills",
    "debts",
    "investments",
    "businesses",
    "dependents",
    "transactions",
    "transaction_corrections",
)


def _has_rows(connection, table_name: str) -> bool:
    return connection.execute(
        sa.text(f"SELECT 1 FROM {table_name} LIMIT 1")
    ).first() is not None


def _add_owner_column(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.add_column(sa.Column("owner_id", sa.String(length=255), nullable=True))


def _make_owner_required(table_name: str) -> None:
    with op.batch_alter_table(table_name) as batch:
        batch.alter_column(
            "owner_id",
            existing_type=sa.String(length=255),
            nullable=False,
        )


def upgrade() -> None:
    connection = op.get_bind()
    populated = {table: _has_rows(connection, table) for table in TABLES}
    legacy_owner_id = (os.getenv("SERENITY_LEGACY_OWNER_ID") or "").strip()
    if any(populated.values()) and not legacy_owner_id:
        raise RuntimeError(
            "SERENITY_LEGACY_OWNER_ID is required when migrating existing "
            "financial records; refusing to guess their owner"
        )

    for table in TABLES:
        _add_owner_column(table)

    if legacy_owner_id:
        for table in (
            "accounts",
            "bills",
            "debts",
            "investments",
            "businesses",
            "dependents",
        ):
            connection.execute(
                sa.text(f"UPDATE {table} SET owner_id = :owner_id"),
                {"owner_id": legacy_owner_id},
            )
        connection.execute(sa.text(
            "UPDATE transactions SET owner_id = ("
            "SELECT accounts.owner_id FROM accounts "
            "WHERE accounts.id = transactions.account_id)"
        ))
        connection.execute(sa.text(
            "UPDATE transaction_corrections SET owner_id = ("
            "SELECT transactions.owner_id FROM transactions "
            "WHERE transactions.id = transaction_corrections.transaction_id)"
        ))

    # Drop these before SQLite's batch rebuild needs to reflect the table:
    # SQLAlchemy cannot reflect expression indexes, which otherwise emits
    # warnings and can lose the indexes silently during the rebuild.
    op.execute(sa.text("DROP INDEX IF EXISTS uq_businesses_name_lower"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_dependents_display_name_lower"))
    for table in TABLES:
        _make_owner_required(table)

    with op.batch_alter_table("businesses") as batch:
        batch.drop_constraint("uq_businesses_name", type_="unique")
        batch.create_unique_constraint(
            "uq_businesses_owner_name", ["owner_id", "name"]
        )
    with op.batch_alter_table("dependents") as batch:
        batch.drop_constraint("uq_dependents_display_name", type_="unique")
        batch.create_unique_constraint(
            "uq_dependents_owner_name", ["owner_id", "display_name"]
        )
    op.create_index(
        "uq_businesses_owner_name_lower",
        "businesses",
        ["owner_id", sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_dependents_owner_name_lower",
        "dependents",
        ["owner_id", sa.text("lower(display_name)")],
        unique=True,
    )


def downgrade() -> None:
    op.execute(sa.text("DROP INDEX IF EXISTS uq_businesses_owner_name_lower"))
    op.execute(sa.text("DROP INDEX IF EXISTS uq_dependents_owner_name_lower"))
    with op.batch_alter_table("businesses") as batch:
        batch.drop_constraint("uq_businesses_owner_name", type_="unique")
        batch.create_unique_constraint("uq_businesses_name", ["name"])
    with op.batch_alter_table("dependents") as batch:
        batch.drop_constraint("uq_dependents_owner_name", type_="unique")
        batch.create_unique_constraint("uq_dependents_display_name", ["display_name"])
    op.create_index(
        "uq_businesses_name_lower",
        "businesses",
        [sa.text("lower(name)")],
        unique=True,
    )
    op.create_index(
        "uq_dependents_display_name_lower",
        "dependents",
        [sa.text("lower(display_name)")],
        unique=True,
    )
    for table in reversed(TABLES):
        with op.batch_alter_table(table) as batch:
            batch.drop_column("owner_id")