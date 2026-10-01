"""Allow portfolio-first drafts; preserve all older investment/account links."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0017_portfolio_holdings"
down_revision: Union[str, None] = "0016_investment_review_drafts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("investments", sa.Column("portfolio_id", sa.Integer(), nullable=True))
    op.create_index("ix_investments_owner_portfolio", "investments", ["owner_id", "portfolio_id"])


def downgrade() -> None:
    if op.get_bind().execute(sa.text(
        "SELECT 1 FROM investments WHERE portfolio_id IS NOT NULL LIMIT 1"
    )).first():
        raise RuntimeError("Cannot downgrade 0017: direct portfolio investments exist")
    op.drop_index("ix_investments_owner_portfolio", table_name="investments")
    with op.batch_alter_table("investments") as batch:
        batch.drop_column("portfolio_id")