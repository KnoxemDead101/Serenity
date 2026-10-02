"""Bounded owner-scoped operational history, with no free-form payload."""

from alembic import context, op
import sqlalchemy as sa

revision = "0026_system_observations"
down_revision = "0025_projects_tasks"
branch_labels = None
depends_on = None


def upgrade():
    # Frozen vocabulary: no dependency on runtime choices or financial tables.
    op.create_table(
        "system_observations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("state", sa.String(11), nullable=False),
        sa.Column("database", sa.String(11), nullable=False),
        sa.Column("schema", sa.String(11), nullable=False),
        sa.Column("write_safety", sa.String(11), nullable=False),
        sa.Column("migration", sa.String(10), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id"], ["workspaces.id"],
            name="fk_system_observations_workspace", ondelete="CASCADE",
        ),
        sa.CheckConstraint("kind IN ('BASELINE', 'TRANSITION')", name="ck_system_observations_kind"),
        sa.CheckConstraint("state IN ('NORMAL', 'READ_ONLY', 'UNAVAILABLE')", name="ck_system_observations_state"),
        sa.CheckConstraint("database IN ('AVAILABLE', 'UNAVAILABLE')", name="ck_system_observations_database"),
        sa.CheckConstraint("schema IN ('AVAILABLE', 'UNAVAILABLE')", name="ck_system_observations_schema"),
        sa.CheckConstraint("write_safety IN ('AVAILABLE', 'READ_ONLY', 'UNAVAILABLE')", name="ck_system_observations_write_safety"),
        sa.CheckConstraint("migration IN ('CURRENT', 'BEHIND', 'UNVERIFIED')", name="ck_system_observations_migration"),
    )
    op.create_index("ix_system_observations_owner_id_id", "system_observations", ["owner_id", "id"])
    op.create_index("ix_system_observations_checked_at", "system_observations", ["checked_at"])


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("History downgrade requires an online preservation check")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE system_observations IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT COUNT(*) FROM system_observations")):
        raise RuntimeError("Cannot downgrade while operational history exists")
    op.drop_table("system_observations")