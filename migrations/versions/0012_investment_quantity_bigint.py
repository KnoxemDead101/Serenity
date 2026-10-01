"""Widen investments.quantity_units to 64-bit for fractional share holdings.

SQLite stores integers as signed 64-bit values regardless of the declared
INTEGER type, so its schema needs no rebuild. PostgreSQL does need a type
alteration; downgrades can fail safely if quantities exceed 32-bit limits.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0012_investment_quantity_bigint"
down_revision: Union[str, None] = "0011_identity_and_workspaces"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "investments",
        "quantity_units",
        existing_type=sa.Integer(),
        type_=sa.BigInteger(),
    )


def downgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    op.alter_column(
        "investments",
        "quantity_units",
        existing_type=sa.BigInteger(),
        type_=sa.Integer(),
    )