"""Restore reviewed ownership safeguards after the first managed Publish."""

from alembic import op

from migrations.publish_key_references import restore_references

revision = "0024_restore_publish_keys"
down_revision = "0023_goal_progress_guard"
branch_labels = None
depends_on = None


def upgrade():
    # Production parent keys are verified separately through read-only queries.
    # This migration runs in development; only managed Publish changes production.
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        restore_references(op)
    elif dialect != "sqlite":
        raise RuntimeError("Ownership restoration requires SQLite or PostgreSQL")
    # SQLite never removed these keys in the staging migration.


def downgrade():
    # Moving the revision pointer back must not silently remove ownership safety.
    # Keep the restored keys, as the historical staging downgrade also does.
    # A new removal requires a separately reviewed staging migration and gate.
    if op.get_bind().dialect.name not in ("postgresql", "sqlite"):
        raise RuntimeError("Ownership restoration requires SQLite or PostgreSQL")