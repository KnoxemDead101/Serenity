"""Database-backed serialization for owner-scoped financial writes.

Call :func:`lock_owner_financial_writes` before reading dependencies that a
financial mutation will validate. The lock is held until the caller commits or
rolls back; this helper deliberately never manages the Session transaction.
"""

from sqlalchemy import text
from sqlalchemy.orm import Session

from services.ownership import require_owner_id


def lock_owner_financial_writes(db: Session, owner_id: str) -> None:
    """Acquire this owner's transaction-scoped financial write lock.

    PostgreSQL uses the same stable owner-keyed transaction advisory lock as
    conversion writes. SQLite starts an immediate write transaction, preventing
    a second writer from passing dependency checks before this transaction
    commits. Existing SQLAlchemy autobegun transactions are supported: on
    SQLite a logical transaction with no DBAPI transaction can still be
    upgraded to ``BEGIN IMMEDIATE``. A pre-existing DBAPI read transaction
    cannot be safely upgraded, so fail closed instead of pretending it is
    serialized.
    """
    owner_id = require_owner_id(owner_id)
    connection = db.connection()
    dialect = connection.dialect.name

    if dialect == "postgresql":
        connection.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:owner_id, 0))"),
            {"owner_id": owner_id},
        )
        return

    if dialect == "sqlite":
        raw_connection = connection.connection.driver_connection
        transaction = db.get_transaction()
        lock_key = "_financial_write_lock_sqlite_transaction"
        # BEGIN IMMEDIATE already acquired the lock if this helper recorded it
        # for the current Session transaction.
        if raw_connection.in_transaction:
            if db.info.get(lock_key) is transaction:
                return
            raise RuntimeError(
                "Cannot acquire the owner financial write lock after a SQLite "
                "database transaction has already started"
            )
        connection.exec_driver_sql("BEGIN IMMEDIATE")
        db.info[lock_key] = transaction
        return

    raise RuntimeError(
        f"Owner financial writes are not supported for database dialect {dialect!r}"
    )