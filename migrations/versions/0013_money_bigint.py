"""Widen stored monetary cents to signed 64-bit integers.

PostgreSQL INTEGER only holds approximately 21.47 million dollars in cents;
validated values can be much larger. SQLite INTEGER already holds signed
64-bit values, so rebuilding its tables would be unnecessary and risky.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0013_money_bigint"
down_revision: Union[str, None] = "0012_investment_quantity_bigint"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Keep this in sync with all mapped *_cents fields in models/.
MONEY_COLUMNS = {
    "accounts": ("opening_balance_cents",),
    "bills": ("amount_cents",),
    "debts": ("balance_cents", "minimum_payment_cents"),
    "investments": ("cost_basis_cents", "current_value_cents"),
    "transactions": ("amount_cents",),
    "income_profiles": (
        "hourly_rate_cents", "annual_salary_cents",
        "amount_per_period_cents", "expected_net_per_period_cents",
    ),
}
MIN_INT32 = -(2 ** 31)
MAX_INT32 = 2 ** 31 - 1


def upgrade() -> None:
    if op.get_bind().dialect.name == "sqlite":
        return
    for table, columns in MONEY_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.Integer(),
                            type_=sa.BigInteger())


def downgrade() -> None:
    connection = op.get_bind()
    # Preflight ALL columns before changing any type. PostgreSQL rejects an
    # out-of-range cast; catching it late would risk a partial downgrade on
    # databases whose DDL is not transactional.
    for table, columns in MONEY_COLUMNS.items():
        for column in columns:
            out_of_range = connection.execute(sa.text(
                f"SELECT 1 FROM {table} WHERE {column} < :min_value "
                f"OR {column} > :max_value LIMIT 1"
            ), {"min_value": MIN_INT32, "max_value": MAX_INT32}).first()
            if out_of_range:
                raise RuntimeError(
                    f"Cannot narrow {table}.{column}: values exceed signed "
                    "32-bit cents; restore from backup or retain migration 0013"
                )
    if connection.dialect.name == "sqlite":
        return
    for table, columns in MONEY_COLUMNS.items():
        for column in columns:
            op.alter_column(table, column, existing_type=sa.BigInteger(),
                            type_=sa.Integer())