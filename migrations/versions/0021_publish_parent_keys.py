"""Expose owner-matched foreign-key targets as actual unique constraints."""

from alembic import op

revision = "0021_publish_parent_keys"
down_revision = "0020_conversion_integration"
branch_labels = None
depends_on = None

PARENT_KEYS = (
    ("accounts", ("owner_id", "id")),
    ("investments", ("owner_id", "id")),
    ("investment_accounts", ("owner_id", "id")),
    ("instruments", ("owner_id", "id")),
    ("instrument_specifications", ("owner_id", "instrument_id", "id")),
)


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # Keep the old ux_* indexes: existing foreign keys depend on them.
        # Additional constraints are additive, preserve every row, and appear
        # in the Publish schema diff. A separate staged release handles ordering.
        for table, columns in PARENT_KEYS:
            op.create_unique_constraint(
                f"uq_{table}_{'_'.join(columns)}", table, list(columns),
            )
    elif dialect != "sqlite":
        raise RuntimeError("Publish parent keys require SQLite or PostgreSQL")
    # SQLite already enforces the equivalent composite unique indexes.
    # Do not rebuild populated tables just to change their representation.


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for table, columns in reversed(PARENT_KEYS):
            # No CASCADE: if another schema writer bound new foreign keys to
            # these constraints, refuse instead of removing those protections.
            op.drop_constraint(
                f"uq_{table}_{'_'.join(columns)}", table, type_="unique",
            )
    elif dialect != "sqlite":
        raise RuntimeError("Publish parent keys require SQLite or PostgreSQL")