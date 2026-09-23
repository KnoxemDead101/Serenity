"""Align transaction semantics and add transaction-level details.

Revision ID: 0004_align_transactions_v02
Revises: 0003_transaction_corrections
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_align_transactions_v02"
down_revision: Union[str, None] = "0003_transaction_corrections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("classification", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("merchant", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("location", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("subcategory", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    op.execute("UPDATE transactions SET transaction_type = 'Income' WHERE transaction_type = 'Deposit'")
    op.execute("UPDATE transactions SET transaction_type = 'Expense' WHERE transaction_type = 'Withdrawal'")
    op.execute(
        "UPDATE transactions SET classification = "
        "(SELECT accounts.classification FROM accounts WHERE accounts.id = transactions.account_id)"
    )
    op.execute("UPDATE transactions SET updated_at = created_at")

    with op.batch_alter_table("transactions") as batch:
        batch.alter_column("classification", existing_type=sa.String(length=50), nullable=False)
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    op.execute("UPDATE transactions SET transaction_type = 'Deposit' WHERE transaction_type = 'Income'")
    op.execute("UPDATE transactions SET transaction_type = 'Withdrawal' WHERE transaction_type = 'Expense'")
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("subcategory")
        batch.drop_column("location")
        batch.drop_column("merchant")
        batch.drop_column("classification")