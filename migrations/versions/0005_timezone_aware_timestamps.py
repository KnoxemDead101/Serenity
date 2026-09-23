"""Make created_at / updated_at time-zone aware.

Revision ID: 0005_timezone_aware_timestamps
Revises: 0004_align_transactions_v02

PostgreSQL changes the existing naive timestamp columns to timestamptz,
interpreting their existing values as UTC. SQLite has no distinct
time-zone-aware timestamp type, so this migration is intentionally a no-op
there.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0005_timezone_aware_timestamps"
down_revision: Union[str, None] = "0004_align_transactions_v02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ["accounts", "bills", "debts", "investments", "transactions"]
COLUMNS = ["created_at", "updated_at"]


def _is_sqlite() -> bool:
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    if _is_sqlite():
        return
    for table in TABLES:
        for column in COLUMNS:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(timezone=True),
                existing_type=sa.DateTime(),
                existing_nullable=False,
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )


def downgrade() -> None:
    if _is_sqlite():
        return
    for table in TABLES:
        for column in COLUMNS:
            op.alter_column(
                table,
                column,
                type_=sa.DateTime(),
                existing_type=sa.DateTime(timezone=True),
                existing_nullable=False,
                postgresql_using=f"{column} AT TIME ZONE 'UTC'",
            )