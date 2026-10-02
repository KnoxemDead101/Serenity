"""Add optional owner-matched work relationships; financial tables are untouched."""

from alembic import context, op
import sqlalchemy as sa

revision = "0025_projects_tasks"
down_revision = "0024_restore_publish_keys"
branch_labels = None
depends_on = None


def _columns():
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("priority", sa.String(8), nullable=False, server_default="NORMAL"),
        sa.Column("status", sa.String(16), nullable=False, server_default="NOT_STARTED"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _constraints(table):
    # Vocabulary is frozen here so future application choices cannot reinterpret
    # this historical migration.
    return [
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'PAUSED', 'CANCELLED')",
            name=f"ck_{table}_status",
        ),
        sa.CheckConstraint(
            "priority IN ('HIGH', 'NORMAL', 'LOW')", name=f"ck_{table}_priority",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name=f"ck_{table}_completed_at_status",
        ),
    ]


def _guards(table, parent, link):
    # Historical SQLite compatibility SQL, independent of mutable model helpers.
    for action, suffix in (("INSERT", "insert"), (f"UPDATE OF owner_id, {link}", "update")):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_owner_{suffix}
            BEFORE {action} ON {table}
            FOR EACH ROW WHEN NEW.{link} IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM {parent} WHERE id = NEW.{link} AND owner_id = NEW.owner_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'Work relationship owner must match its source');
            END
        """)
    op.execute(f"""
        CREATE TRIGGER trg_{parent}_restrict_{table}_delete
        BEFORE DELETE ON {parent}
        FOR EACH ROW WHEN EXISTS (SELECT 1 FROM {table} WHERE {link} = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Unlink work records before deleting their source');
        END
    """)
    op.execute(f"""
        CREATE TRIGGER trg_{parent}_restrict_{table}_identity_update
        BEFORE UPDATE OF id, owner_id ON {parent}
        FOR EACH ROW WHEN (NEW.id IS NOT OLD.id OR NEW.owner_id IS NOT OLD.owner_id)
            AND EXISTS (SELECT 1 FROM {table} WHERE {link} = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Cannot change a source identity with linked work');
        END
    """)


def upgrade():
    op.create_table(
        "projects", *_columns(),
        sa.Column("goal_id", sa.Integer(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        *_constraints("projects"),
        sa.UniqueConstraint("owner_id", "id", name="uq_projects_owner_id_id"),
        sa.ForeignKeyConstraint(
            ["owner_id", "goal_id"], ["goals.owner_id", "goals.id"],
            name="fk_projects_owner_goal", ondelete="RESTRICT",
        ),
    )
    op.create_table(
        "tasks", *_columns(),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("due_date", sa.Date(), nullable=True),
        *_constraints("tasks"),
        sa.ForeignKeyConstraint(
            ["owner_id", "project_id"], ["projects.owner_id", "projects.id"],
            name="fk_tasks_owner_project", ondelete="RESTRICT",
        ),
    )
    for table, parent, link in (
        ("projects", "goals", "goal_id"), ("tasks", "projects", "project_id"),
    ):
        op.create_index(f"ix_{table}_owner_id", table, ["owner_id"])
        op.create_index(f"ix_{table}_{link}", table, [link])
        if op.get_bind().dialect.name == "sqlite":
            _guards(table, parent, link)


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Work downgrade requires an online empty-table preservation check")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        # Block new work before checking either table; all checks precede drops.
        connection.execute(sa.text(
            "LOCK TABLE goals, projects, tasks IN ACCESS EXCLUSIVE MODE"
        ))
    for table in ("projects", "tasks"):
        if connection.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError("Cannot downgrade while Projects or Tasks exist, including archived work")
    if connection.dialect.name == "sqlite":
        for table, parent in (("projects", "goals"), ("tasks", "projects")):
            for suffix in ("delete", "identity_update"):
                op.execute(f"DROP TRIGGER trg_{parent}_restrict_{table}_{suffix}")
    op.drop_table("tasks")
    op.drop_table("projects")