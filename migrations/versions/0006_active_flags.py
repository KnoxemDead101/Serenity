"""Add active flags to bills, debts and investments.

Existing records start active. Records are deactivated rather than deleted so
historical information remains available.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0006_active_flags"
down_revision: Union[str, None] = "0005_timezone_aware_timestamps"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("bills", "debts", "investments")


def upgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.add_column(
                sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true())
            )


def downgrade() -> None:
    for table in TABLES:
        with op.batch_alter_table(table) as batch:
            batch.drop_column("active")