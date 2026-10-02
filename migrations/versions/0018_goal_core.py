"""Add standalone owner-private Goal Core; do not modify existing tables."""

from alembic import op
import sqlalchemy as sa

revision = "0018_goal_core"
down_revision = "0017_portfolio_holdings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Freeze this migration's vocabulary so future option-list changes cannot
    # silently change what this historical schema revision means.
    op.create_table(
        "goals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("goal_type", sa.String(32), nullable=False),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="NOT_STARTED"),
        sa.Column("priority", sa.String(8), nullable=False, server_default="NORMAL"),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("target_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("progress_source", sa.String(32), nullable=False, server_default="MANUAL"),
        sa.Column("current_progress_amount_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "id", name="uq_goals_owner_id_id"),
        sa.CheckConstraint(
            "goal_type IN ('SAVINGS', 'DEBT_REDUCTION', 'PURCHASE', 'SPENDING_BUDGET', "
            "'INVESTMENT', 'INCOME', 'GENERAL_FINANCIAL', 'NONFINANCIAL')",
            name="ck_goals_goal_type",
        ),
        sa.CheckConstraint(
            "category IN ('FINANCIAL', 'CAREER', 'BUSINESS', 'FAMILY', 'INVESTING', 'TRADING', 'OTHER')",
            name="ck_goals_category",
        ),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'PAUSED', 'CANCELLED')",
            name="ck_goals_status",
        ),
        sa.CheckConstraint("priority IN ('HIGH', 'NORMAL', 'LOW')", name="ck_goals_priority"),
        sa.CheckConstraint(
            "progress_source IN ('MANUAL', 'TRANSACTION_ACTIVITY', 'ACCOUNT_BALANCE', "
            "'DEBT_BALANCE', 'PORTFOLIO_VALUE', 'INVESTMENT_ACCOUNT', 'BUSINESS_METRIC', 'MILESTONES')",
            name="ck_goals_progress_source",
        ),
        sa.CheckConstraint(
            "target_amount_cents IS NULL OR target_amount_cents BETWEEN 0 AND 100000000000000",
            name="ck_goals_target_amount_cents",
        ),
        sa.CheckConstraint(
            "current_progress_amount_cents IS NULL OR "
            "current_progress_amount_cents BETWEEN 0 AND 100000000000000",
            name="ck_goals_current_progress_amount_cents",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_goals_completed_at_status",
        ),
    )
    op.create_index("ix_goals_owner_id", "goals", ["owner_id"])


def downgrade() -> None:
    # Never discard a user's goals just to make a downgrade succeed.
    if op.get_bind().execute(sa.text("SELECT COUNT(*) FROM goals")).scalar():
        raise RuntimeError("Cannot downgrade Goal Core while goals exist")
    op.drop_index("ix_goals_owner_id", table_name="goals")
    op.drop_table("goals")