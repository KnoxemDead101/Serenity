"""Add private portfolio containers without modifying existing financial rows."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0015_portfolio_containers"
down_revision: Union[str, None] = "0014_instrument_registry"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A composite target index avoids rebuilding accounts (and its legacy
    # expression indexes) on SQLite; old owner/id values remain untouched.
    op.create_index("ux_accounts_owner_id_id", "accounts", ["owner_id", "id"], unique=True)
    op.create_table(
        "portfolios",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "id", name="uq_portfolios_owner_id_id"),
    )
    op.create_index("ix_portfolios_owner_id", "portfolios", ["owner_id"])
    op.create_table(
        "investment_accounts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(length=255), nullable=False),
        sa.Column("portfolio_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("notes", sa.Text()),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "portfolio_id"], ["portfolios.owner_id", "portfolios.id"],
            name="fk_investment_accounts_owner_portfolio", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "account_id"], ["accounts.owner_id", "accounts.id"],
            name="fk_investment_accounts_owner_account", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("account_id", name="uq_investment_accounts_account_id"),
    )
    op.create_index("ix_investment_accounts_owner_id", "investment_accounts", ["owner_id"])
    op.create_index("ix_investment_accounts_owner_portfolio", "investment_accounts", ["owner_id", "portfolio_id"])


def downgrade() -> None:
    connection = op.get_bind()
    for table in ("investment_accounts", "portfolios"):
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                f"Cannot downgrade 0015: {table} contains portfolio history; "
                "retain the migration or export and remove data intentionally"
            )
    op.drop_index("ix_investment_accounts_owner_portfolio", table_name="investment_accounts")
    op.drop_index("ix_investment_accounts_owner_id", table_name="investment_accounts")
    op.drop_table("investment_accounts")
    op.drop_index("ix_portfolios_owner_id", table_name="portfolios")
    op.drop_table("portfolios")
    op.drop_index("ux_accounts_owner_id_id", table_name="accounts")