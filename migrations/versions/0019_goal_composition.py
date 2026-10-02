"""Add owner-matched Goal composition, without changing financial tables."""

from alembic import context, op
import sqlalchemy as sa

revision = "0019_goal_composition"
down_revision = "0018_goal_core"
branch_labels = None
depends_on = None

TABLES = ("goal_items", "goal_milestones", "goal_checkpoints")


def _common_columns() -> list:
    return [
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("goal_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    ]


def _common_constraints(table: str) -> list:
    return [
        sa.ForeignKeyConstraint(
            ["owner_id", "goal_id"], ["goals.owner_id", "goals.id"],
            name=f"fk_{table}_owner_goal", ondelete="RESTRICT",
        ),
        sa.CheckConstraint(
            "sort_order BETWEEN 0 AND 2147483647", name=f"ck_{table}_sort_order",
        ),
    ]


def _sqlite_guard_statements(table: str) -> list[str]:
    # Freeze SQLite's compatibility guards in this historical migration too;
    # never import mutable application helpers into the schema history.
    statements = []
    for action, suffix in (("INSERT", "insert"), ("UPDATE OF owner_id, goal_id", "update")):
        statements.append(f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_owner_{suffix}
            BEFORE {action} ON {table}
            FOR EACH ROW WHEN NOT EXISTS (
                SELECT 1 FROM goals WHERE id = NEW.goal_id AND owner_id = NEW.owner_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'Goal composition owner must match its parent Goal');
            END
        """)
    statements.append(f"""
        CREATE TRIGGER IF NOT EXISTS trg_goals_restrict_{table}_delete
        BEFORE DELETE ON goals
        FOR EACH ROW WHEN EXISTS (SELECT 1 FROM {table} WHERE goal_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Explicitly remove Goal composition before deleting its Goal');
        END
    """)
    statements.append(f"""
        CREATE TRIGGER IF NOT EXISTS trg_goals_restrict_{table}_identity_update
        BEFORE UPDATE OF id, owner_id ON goals
        FOR EACH ROW WHEN
            (NEW.id IS NOT OLD.id OR NEW.owner_id IS NOT OLD.owner_id)
            AND EXISTS (SELECT 1 FROM {table} WHERE goal_id = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Cannot change the identity of a Goal with composition');
        END
    """)
    return statements


def upgrade() -> None:
    # Historical status/money constraints are frozen here, not imported from
    # mutable application choice lists. All three money columns are BIGINT.
    op.create_table(
        "goal_items",
        *_common_columns(),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("expected_cost_cents", sa.BigInteger(), nullable=True),
        sa.Column("manual_actual_cost_override_cents", sa.BigInteger(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="PLANNED"),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_common_constraints("goal_items"),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'CANCELLED')",
            name="ck_goal_items_status",
        ),
        sa.CheckConstraint(
            "expected_cost_cents IS NULL OR expected_cost_cents BETWEEN 0 AND 100000000000000",
            name="ck_goal_items_expected_cost_cents",
        ),
        sa.CheckConstraint(
            "manual_actual_cost_override_cents IS NULL OR "
            "manual_actual_cost_override_cents BETWEEN 0 AND 100000000000000",
            name="ck_goal_items_manual_actual_cost_override_cents",
        ),
    )
    op.create_table(
        "goal_milestones",
        *_common_columns(),
        sa.Column("title", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("target_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="NOT_STARTED"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        *_common_constraints("goal_milestones"),
        sa.CheckConstraint(
            "status IN ('NOT_STARTED', 'IN_PROGRESS', 'COMPLETED', 'SKIPPED', 'CANCELLED')",
            name="ck_goal_milestones_status",
        ),
        sa.CheckConstraint(
            "(status = 'COMPLETED' AND completed_at IS NOT NULL) OR "
            "(status <> 'COMPLETED' AND completed_at IS NULL)",
            name="ck_goal_milestones_completed_at_status",
        ),
    )
    op.create_table(
        "goal_checkpoints",
        *_common_columns(),
        sa.Column("amount_cents", sa.BigInteger(), nullable=False),
        sa.Column("label", sa.String(100), nullable=True),
        *_common_constraints("goal_checkpoints"),
        sa.CheckConstraint(
            "amount_cents BETWEEN 0 AND 100000000000000",
            name="ck_goal_checkpoints_amount_cents",
        ),
    )
    for table in TABLES:
        op.create_index(
            f"ix_{table}_owner_goal_order", table,
            ["owner_id", "goal_id", "sort_order", "id"],
        )
        op.create_index(f"ix_{table}_goal_id", table, ["goal_id"])
    if op.get_bind().dialect.name == "sqlite":
        # Do not enable FK checks globally: that would also change financial
        # tables. Enforce this composite relationship with Goal-only guards.
        for table in TABLES:
            for statement in _sqlite_guard_statements(table):
                op.execute(statement)


def downgrade() -> None:
    if context.is_offline_mode():
        raise RuntimeError(
            "A live database connection is required to verify Goal Composition "
            "tables are empty before downgrade"
        )
    bind = op.get_bind()
    # Serialize PostgreSQL writers during the complete preservation preflight.
    # SQLite migrations remain maintenance operations with app writers stopped,
    # following existing repository behavior rather than changing shared setup.
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text(
            "LOCK TABLE goals, goal_items, goal_milestones, goal_checkpoints IN ACCESS EXCLUSIVE MODE"
        ))
    # Check EVERY table before dropping anything: even an archived/cancelled
    # record is user planning data. Parent Goals alone are safe to preserve.
    for table in TABLES:
        if bind.execute(sa.text(f"SELECT COUNT(*) FROM {table}")).scalar():
            raise RuntimeError(
                f"Cannot downgrade Goal Composition while {table} records exist; "
                "preserve and explicitly remove them before retrying"
            )
    for table in reversed(TABLES):
        if bind.dialect.name == "sqlite":
            for suffix in ("delete", "identity_update"):
                op.execute(f"DROP TRIGGER IF EXISTS trg_goals_restrict_{table}_{suffix}")
        op.drop_index(f"ix_{table}_owner_goal_order", table_name=table)
        op.drop_index(f"ix_{table}_goal_id", table_name=table)
        op.drop_table(table)