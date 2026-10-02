"""Approved temporary FK staging; application writes must fail closed."""

from alembic import op

from migrations.publish_key_references import REFERENCES, restore_references

revision = "0022_publish_key_stage"
down_revision = "0021_publish_parent_keys"
branch_labels = None
depends_on = None


def upgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        for table, name, *_ in REFERENCES:
            op.drop_constraint(name, table, type_="foreignkey")
    elif dialect != "sqlite":
        raise RuntimeError("Publish staging requires SQLite or PostgreSQL")
    # Local SQLite is not the managed Publish source. Leave its safeguards intact.


def downgrade():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        restore_references(op)
    elif dialect != "sqlite":
        raise RuntimeError("Publish staging requires SQLite or PostgreSQL")