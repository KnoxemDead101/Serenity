"""Create owner-scoped income profiles."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0010_income_profiles"
down_revision: Union[str, None] = "0009_owner_id_indexes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "income_profiles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("income_type", sa.String(length=20), nullable=False),
        sa.Column("classification", sa.String(length=20), nullable=False),
        sa.Column("pay_frequency", sa.String(length=20), nullable=True),
        sa.Column("hourly_rate_cents", sa.Integer(), nullable=True),
        sa.Column("standard_hours_hundredths", sa.Integer(), nullable=True),
        sa.Column("expected_hours_hundredths", sa.Integer(), nullable=True),
        sa.Column("annual_salary_cents", sa.Integer(), nullable=True),
        sa.Column("amount_per_period_cents", sa.Integer(), nullable=True),
        sa.Column("expected_net_per_period_cents", sa.Integer(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_income_profiles_owner_id", "income_profiles", ["owner_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_income_profiles_owner_id", table_name="income_profiles")
    op.drop_table("income_profiles")