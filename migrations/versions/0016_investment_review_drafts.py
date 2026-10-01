"""Add uncounted, container-assigned investment candidates without backfilling."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_investment_review_drafts"
down_revision: Union[str, None] = "0015_portfolio_containers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("investments", sa.Column("investment_account_id", sa.Integer(), nullable=True))
    op.add_column("investments", sa.Column(
        "review_pending", sa.Boolean(), nullable=False, server_default=sa.false()
    ))
    op.create_index("ix_investments_owner_container", "investments", ["owner_id", "investment_account_id"])


def downgrade() -> None:
    connection = op.get_bind()
    if connection.execute(sa.text(
        "SELECT 1 FROM investments WHERE review_pending = :pending "
        "OR investment_account_id IS NOT NULL LIMIT 1"
    ), {"pending": True}).first():
        raise RuntimeError("Cannot downgrade 0016: assigned investment drafts exist")
    op.drop_index("ix_investments_owner_container", table_name="investments")
    with op.batch_alter_table("investments") as batch:
        batch.drop_column("review_pending")
        batch.drop_column("investment_account_id")