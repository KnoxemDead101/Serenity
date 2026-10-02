"""Read-only schema safety checks; never create or alter database objects."""

from sqlalchemy import inspect, text

from migrations.publish_key_references import REFERENCES

MESSAGE = (
    "Serenity is temporarily read-only while the publishing repair is completed. "
    "Your records are preserved. Writes resume only after ownership protections "
    "are restored."
)


class WritesPaused(RuntimeError):
    pass


def write_state(connection, *, lock=False):
    if connection.dialect.name == "sqlite":
        return "NORMAL"
    if connection.dialect.name != "postgresql":
        return "READ_ONLY"
    try:
        # Historical pre-conversion schemas retain their legacy finance behavior.
        # The staged Publish creates this ledger, so it cannot take that branch.
        if connection.scalar(text(
            "SELECT to_regclass('public.reconciliation_approvals')"
        )) is None:
            return "NORMAL"
        inspector = inspect(connection)
        tables = sorted({item[0] for item in REFERENCES})
        if not all(inspector.has_table(table, schema="public") for table in tables):
            return "READ_ONLY"
        if lock:
            # Prevent a concurrent DROP CONSTRAINT between validation and DML.
            # Held until the caller commits/rolls back. No DDL or data mutation.
            connection.execute(text(
                "LOCK TABLE " + ", ".join(f'public."{t}"' for t in tables)
                + " IN ROW SHARE MODE"
            ))
        validated = {
            tuple(row) for row in connection.execute(text(
                "SELECT r.relname, c.conname FROM pg_constraint c "
                "JOIN pg_class r ON r.oid = c.conrelid "
                "JOIN pg_namespace n ON n.oid = c.connamespace "
                "WHERE n.nspname = 'public' AND c.contype = 'f' AND c.convalidated"
            ))
        }
        actual = {
            (table, fk["name"]): fk
            for table in tables
            for fk in inspect(connection).get_foreign_keys(table, schema="public")
        }
        for table, name, columns, parent, parent_columns in REFERENCES:
            fk = actual.get((table, name))
            if not fk or (table, name) not in validated:
                return "READ_ONLY"
            if (
                tuple(fk["constrained_columns"]) != columns
                or fk["referred_table"] != parent
                or fk["referred_schema"] not in (None, "public")
                or tuple(fk["referred_columns"]) != parent_columns
                or fk["options"].get("ondelete") != "RESTRICT"
            ):
                return "READ_ONLY"
        return "NORMAL"
    except Exception:
        # No silent assumption of safety and no raw database error in responses.
        return "READ_ONLY"


def require_safe_write(db):
    if write_state(db.connection(), lock=True) != "NORMAL":
        raise WritesPaused(MESSAGE)


def protect_flush(db, flush_context, instances):
    if any(
        getattr(obj, "__table__", None) is not None
        and "owner_id" in obj.__table__.c
        for obj in (*db.new, *db.dirty, *db.deleted)
    ):
        require_safe_write(db)


def protect_bulk(execution):
    if execution.is_insert or execution.is_update or execution.is_delete:
        table = getattr(execution.statement, "table", None)
        if table is not None and "owner_id" in table.c:
            require_safe_write(execution.session)