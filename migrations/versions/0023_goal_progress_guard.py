"""Require null stored progress for reserved Goal sources; preserve all rows."""

from alembic import context, op
import sqlalchemy as sa

revision = "0023_goal_progress_guard"
down_revision = "0022_publish_key_stage"
branch_labels = None
depends_on = None

CONSTRAINT = "ck_goals_manual_progress_only"
RULE = "progress_source = 'MANUAL' OR current_progress_amount_cents IS NULL"


def _prepare_connection():
    if context.is_offline_mode():
        raise RuntimeError(
            "A live development connection is required to preserve Goal records"
        )
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        # Keep the preflight and constraint addition atomic against writers.
        bind.execute(sa.text("LOCK TABLE goals IN ACCESS EXCLUSIVE MODE"))
    elif bind.dialect.name == "sqlite":
        # A table rebuild with enabled foreign keys can delete child records.
        # Alembic's normal SQLite connection leaves foreign keys disabled.
        if bind.exec_driver_sql("PRAGMA foreign_keys").scalar():
            raise RuntimeError(
                "Goal progress migration requires SQLite maintenance with "
                "writers stopped and foreign_keys disabled on this connection"
            )
        # SQLite's legacy driver does not start transactions for SELECT/DDL.
        # Explicitly include the rebuild and trigger restoration in one.
        if not bind.connection.driver_connection.in_transaction:
            bind.exec_driver_sql("BEGIN IMMEDIATE")
    else:
        raise RuntimeError("Goal progress migration requires SQLite or PostgreSQL")
    return bind


def _change_constraint(bind, *, add):
    if bind.dialect.name == "postgresql":
        if add:
            op.create_check_constraint(CONSTRAINT, "goals", RULE)
        else:
            op.drop_constraint(CONSTRAINT, "goals", type_="check")
        return

    # Rebuilding the parent loses its triggers, and child triggers referencing
    # a temporarily absent parent can block SQLite's rename. Preserve the exact
    # existing guards, rather than importing mutable application definitions.
    triggers = bind.execute(sa.text(
        "SELECT name, sql FROM sqlite_master WHERE type = 'trigger' "
        "AND tbl_name IN ('goals', 'goal_items', 'goal_milestones', 'goal_checkpoints') "
        "ORDER BY name"
    )).all()
    for name, _ in triggers:
        quoted_name = bind.dialect.identifier_preparer.quote_identifier(name)
        bind.exec_driver_sql(f"DROP TRIGGER {quoted_name}")
    with op.batch_alter_table("goals", recreate="always") as batch:
        if add:
            batch.create_check_constraint(CONSTRAINT, RULE)
        else:
            batch.drop_constraint(CONSTRAINT, type_="check")
    for _, statement in triggers:
        bind.exec_driver_sql(statement)


def upgrade() -> None:
    bind = _prepare_connection()
    # Include every date, archived records, and non-null zero. Do not expose
    # record details or silently clear amounts/relabel sources to pass migration.
    if bind.execute(sa.text(
        "SELECT 1 FROM goals WHERE progress_source <> 'MANUAL' "
        "AND current_progress_amount_cents IS NOT NULL LIMIT 1"
    )).first():
        raise RuntimeError(
            "Cannot enforce Goal progress constraint while unsupported stored "
            "progress exists; preserve records and obtain explicit owner review"
        )
    _change_constraint(bind, add=True)


def downgrade() -> None:
    # Removing only this check never deletes or rewrites historical Goal data.
    _change_constraint(_prepare_connection(), add=False)