"""Align transactions with the v0.2 handoff.

Revision ID: 0004_align_transactions_v02
Revises: 0003_transaction_corrections

What this migration does, step by step:

1. Adds new columns: classification, merchant, location, subcategory,
   updated_at. They start out nullable so existing rows are allowed.
2. DATA CHANGE: renames the transaction types
       Deposit    -> Income
       Withdrawal -> Expense
   Amounts don't change; they were already stored positive.
3. DATA CHANGE: fills each existing transaction's classification with its
   account's classification, and its updated_at with its created_at.
4. Makes classification and updated_at required (NOT NULL) now that every
   row has a value.

The correction history (transaction_corrections) is NOT rewritten: old
snapshots keep saying "Deposit"/"Withdrawal", because history records what
was true at the time.

`batch_alter_table` lets the same code work on SQLite (which can't alter
columns directly, so Alembic rebuilds the table) and PostgreSQL.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0004_align_transactions_v02"
down_revision: Union[str, None] = "0003_transaction_corrections"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Step 1: new columns (nullable for now).
    with op.batch_alter_table("transactions") as batch:
        batch.add_column(sa.Column("classification", sa.String(length=50), nullable=True))
        batch.add_column(sa.Column("merchant", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("location", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("subcategory", sa.String(length=100), nullable=True))
        batch.add_column(sa.Column("updated_at", sa.DateTime(), nullable=True))

    # Step 2: rename the direction values.
    op.execute(
        "UPDATE transactions SET transaction_type = 'Income' "
        "WHERE transaction_type = 'Deposit'"
    )
    op.execute(
        "UPDATE transactions SET transaction_type = 'Expense' "
        "WHERE transaction_type = 'Withdrawal'"
    )
    # Step 3: backfill the new required values.
    op.execute(
        "UPDATE transactions SET classification = ("
        "SELECT accounts.classification FROM accounts "
        "WHERE accounts.id = transactions.account_id)"
    )
    op.execute("UPDATE transactions SET updated_at = created_at")

    # Step 4: now every row has values, so require them.
    with op.batch_alter_table("transactions") as batch:
        batch.alter_column(
            "classification", existing_type=sa.String(length=50), nullable=False
        )
        batch.alter_column("updated_at", existing_type=sa.DateTime(), nullable=False)


def downgrade() -> None:
    op.execute(
        "UPDATE transactions SET transaction_type = 'Deposit' "
        "WHERE transaction_type = 'Income'"
    )
    op.execute(
        "UPDATE transactions SET transaction_type = 'Withdrawal' "
        "WHERE transaction_type = 'Expense'"
    )
    with op.batch_alter_table("transactions") as batch:
        batch.drop_column("updated_at")
        batch.drop_column("subcategory")
        batch.drop_column("location")
        batch.drop_column("merchant")
        batch.drop_column("classification")