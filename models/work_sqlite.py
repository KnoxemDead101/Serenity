"""Narrow SQLite ownership guards under Serenity's unchanged connection policy."""

from sqlalchemy import DDL, event


def work_guard_statements(table: str, parent: str, link: str) -> list[str]:
    """Nullable links allow standalone work, never foreign-owned relationships."""
    statements = []
    for action, suffix in (("INSERT", "insert"), (f"UPDATE OF owner_id, {link}", "update")):
        statements.append(f"""
            CREATE TRIGGER IF NOT EXISTS trg_{table}_owner_{suffix}
            BEFORE {action} ON {table}
            FOR EACH ROW WHEN NEW.{link} IS NOT NULL AND NOT EXISTS (
                SELECT 1 FROM {parent} WHERE id = NEW.{link} AND owner_id = NEW.owner_id
            )
            BEGIN
                SELECT RAISE(ABORT, 'Work relationship owner must match its source');
            END
        """)
    statements.append(f"""
        CREATE TRIGGER IF NOT EXISTS trg_{parent}_restrict_{table}_delete
        BEFORE DELETE ON {parent}
        FOR EACH ROW WHEN EXISTS (SELECT 1 FROM {table} WHERE {link} = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Unlink work records before deleting their source');
        END
    """)
    statements.append(f"""
        CREATE TRIGGER IF NOT EXISTS trg_{parent}_restrict_{table}_identity_update
        BEFORE UPDATE OF id, owner_id ON {parent}
        FOR EACH ROW WHEN (NEW.id IS NOT OLD.id OR NEW.owner_id IS NOT OLD.owner_id)
            AND EXISTS (SELECT 1 FROM {table} WHERE {link} = OLD.id)
        BEGIN
            SELECT RAISE(ABORT, 'Cannot change a source identity with linked work');
        END
    """)
    return statements


def register_work_guards(table, parent: str, link: str) -> None:
    for statement in work_guard_statements(table.name, parent, link):
        event.listen(table, "after_create", DDL(statement).execute_if(dialect="sqlite"))