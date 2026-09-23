"""Add business/dependent labels and optional transaction links."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0007_business_and_dependents"
down_revision: Union[str, None] = "0006_active_flags"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "businesses",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("name", name="uq_businesses_name"),
    )
    op.create_index(
        "uq_businesses_name_lower", "businesses", [sa.text("lower(name)")], unique=True
    )
    op.create_table(
        "dependents",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("display_name", sa.String(100), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("display_name", name="uq_dependents_display_name"),
    )
    op.create_index(
        "uq_dependents_display_name_lower",
        "dependents",
        [sa.text("lower(display_name)")],
        unique=True,
    )
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("business_id", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("dependent_id", sa.Integer(), nullable=True))
        batch.create_foreign_key(
            "fk_transactions_business_id", "businesses", ["business_id"], ["id"]
        )
        batch.create_foreign_key(
            "fk_transactions_dependent_id", "dependents", ["dependent_id"], ["id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.drop_constraint("fk_transactions_dependent_id", type_="foreignkey")
        batch.drop_constraint("fk_transactions_business_id", type_="foreignkey")
        batch.drop_column("dependent_id")
        batch.drop_column("business_id")
    op.drop_index("uq_dependents_display_name_lower", table_name="dependents")
    op.drop_index("uq_businesses_name_lower", table_name="businesses")
    op.drop_table("dependents")
    op.drop_table("businesses")