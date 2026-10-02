"""Enforce Goal's composite relationships without changing legacy SQLite policy."""

from sqlalchemy import DDL, event


def _guard_statements(table: str) -> list[str]:
    """Mirror the declared composite FK for this planning table only."""
    if table not in ("goal_items", "goal_milestones", "goal_checkpoints"):
        raise ValueError("SQLite Goal guards require a Goal composition table")
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


def register_sqlite_goal_guards(table) -> None:
    # The app's existing SQLite connections leave FK enforcement off. Changing
    # that global policy could alter legacy financial behavior, so these guards
    # enforce the same composite relationship only for the new Goal records.
    # PostgreSQL continues to enforce the ordinary composite FK directly.
    for statement in _guard_statements(table.name):
        event.listen(table, "after_create", DDL(statement).execute_if(dialect="sqlite"))
    # Parent triggers live on Goals, not the child. Remove them if a metadata
    # caller explicitly drops this empty child table to avoid dangling triggers.
    for suffix in ("delete", "identity_update"):
        statement = f"DROP TRIGGER IF EXISTS trg_goals_restrict_{table.name}_{suffix}"
        event.listen(table, "after_drop", DDL(statement).execute_if(dialect="sqlite"))