"""Add owner_id lookup indexes declared by the models."""

from typing import Sequence, Union

from alembic import op

revision: str = "0009_owner_id_indexes"
down_revision: Union[str, None] = "0008_record_ownership"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

OWNER_INDEXES = (
    ("ix_accounts_owner_id", "accounts"),
    ("ix_bills_owner_id", "bills"),
    ("ix_debts_owner_id", "debts"),
    ("ix_investments_owner_id", "investments"),
    ("ix_transactions_owner_id", "transactions"),
    ("ix_transaction_corrections_owner_id", "transaction_corrections"),
)


def upgrade() -> None:
    for index_name, table in OWNER_INDEXES:
        op.create_index(index_name, table, ["owner_id"], if_not_exists=True)


def downgrade() -> None:
    for index_name, table in reversed(OWNER_INDEXES):
        op.drop_index(index_name, table_name=table, if_exists=True)