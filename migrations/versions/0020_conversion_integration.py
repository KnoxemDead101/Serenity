"""Merge conversion and Goals/draft branches without rewriting revision history."""

from alembic import op
import sqlalchemy as sa

revision = "0020_conversion_integration"
down_revision = ("0017_conversion_guards", "0019_goal_composition")
branch_labels = None
depends_on = None

GOAL_TABLES = ("goals", "goal_items", "goal_milestones", "goal_checkpoints")
CONVERSION_TABLES = (
    "reconciliation_approvals", "opening_positions", "valuation_eligibility",
    "cash_reconciliation_entries", "conversion_events",
)


def upgrade():
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        for table in GOAL_TABLES:
            op.execute(f"""
                CREATE TRIGGER trg_conversion_owner_write
                BEFORE INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION conversion_owner_write_lock()
            """)
    elif connection.dialect.name == "sqlite":
        # A sibling branch can recreate investments during SQLite migration.
        # Restore source backstops if that recreation dropped table triggers.
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER IF NOT EXISTS trg_converted_source_no_{operation.lower()}
                BEFORE {operation} ON investments
                WHEN EXISTS (
                    SELECT 1 FROM valuation_eligibility
                    WHERE owner_id = OLD.owner_id AND source_investment_id = OLD.id
                      AND representation = 'opening' AND status = 'active'
                )
                BEGIN SELECT RAISE(ABORT, 'converted original investment is read-only'); END
            """)
    else:
        raise RuntimeError("Conversion integration requires SQLite or PostgreSQL")


def downgrade():
    connection = op.get_bind()
    for table in CONVERSION_TABLES:
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                f"Cannot downgrade conversion integration: conversion history exists in {table}"
            )
    if connection.dialect.name == "postgresql":
        for table in GOAL_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_conversion_owner_write ON {table}")