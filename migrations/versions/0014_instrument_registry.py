"""Add workspace-private instruments with immutable versioned specifications.

No existing financial records are modified. Refuse destructive rollback when
instrument data exists; export/backup and remove it deliberately first.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0014_instrument_registry"
down_revision: Union[str, None] = "0013_money_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "instruments",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "symbol", name="uq_instruments_owner_symbol"),
    )
    op.create_index("ix_instruments_owner_id", "instruments", ["owner_id"])
    op.create_table(
        "instrument_specifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("instrument_id", sa.Integer(), sa.ForeignKey("instruments.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("asset_type", sa.String(length=10), nullable=False),
        sa.Column("exchange", sa.String(length=100)),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("tick_size_units", sa.BigInteger(), nullable=False),
        sa.Column("point_value_units", sa.BigInteger(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("instrument_id", "version", name="uq_instrument_specifications_version"),
    )
    op.create_index("ix_instrument_specifications_owner_id", "instrument_specifications", ["owner_id"])


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("instrument_specifications", "instruments"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                f"Cannot downgrade 0014: {table} contains instrument history; "
                "retain the migration or export and remove data intentionally"
            )
    op.drop_index("ix_instrument_specifications_owner_id", table_name="instrument_specifications")
    op.drop_table("instrument_specifications")
    op.drop_index("ix_instruments_owner_id", table_name="instruments")
    op.drop_table("instruments")