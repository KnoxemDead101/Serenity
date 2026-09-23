"""Preserve transaction edits and deletions.

Revision ID: 0003_transaction_corrections
Revises: 0002_account_transactions
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003_transaction_corrections"
down_revision: Union[str, None] = "0002_account_transactions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        "transaction_corrections",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("account_id", sa.Integer(), sa.ForeignKey("accounts.id"), nullable=False),
        sa.Column(
            "transaction_id", sa.Integer(), sa.ForeignKey("transactions.id"), nullable=False
        ),
        sa.Column("action", sa.String(length=10), nullable=False),
        sa.Column("changed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("before", sa.JSON(), nullable=False),
        sa.Column("after", sa.JSON(), nullable=True),
    )
    op.create_index(
        "ix_transaction_corrections_account_changed",
        "transaction_corrections",
        ["account_id", "changed_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_transaction_corrections_account_changed",
        table_name="transaction_corrections",
    )
    op.drop_table("transaction_corrections")
    op.drop_column("transactions", "deleted_at")