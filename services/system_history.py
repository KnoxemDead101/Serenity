"""Allowlisted, owner-scoped transitions; no exceptions or payloads are logged.

Only console requests generate evidence. Core DML here is intentionally
separate from financial write safety: audit availability is not write authority.
"""

from datetime import datetime, timedelta, timezone

from sqlalchemy import delete, insert, select, update

from models.identity import Workspace
from models.system_observation import SystemObservation

RETENTION_DAYS = 90
MAX_ENTRIES = 200
VOCABULARY = {
    "state": {"NORMAL", "READ_ONLY", "UNAVAILABLE"},
    "database": {"AVAILABLE", "UNAVAILABLE"},
    "schema": {"AVAILABLE", "UNAVAILABLE"},
    "write_safety": {"AVAILABLE", "READ_ONLY", "UNAVAILABLE"},
    "migration": {"CURRENT", "BEHIND", "UNVERIFIED"},
}
TABLE = SystemObservation.__table__


def utc(value):
    """SQLite persisted naive timestamps represent UTC, not local time."""
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def snapshot(report):
    checks = {item["key"]: item["status"] for item in report["checks"]}
    result = {
        "state": report["state"], "database": checks["database"],
        "schema": checks["schema"], "write_safety": checks["write_safety"],
        "migration": report["migration"]["status"],
    }
    validate(result)
    return result


def validate(values):
    for key, allowed in VOCABULARY.items():
        if values[key] not in allowed:
            raise ValueError("Invalid operational evidence")


def lock_owner(connection, owner_id):
    # An existing identity-backed workspace is the concurrency anchor. UPDATE
    # also serializes SQLite writers; PostgreSQL takes a row lock. This changes
    # no identity value and bypasses no financial record guard.
    result = connection.execute(
        update(Workspace.__table__).where(Workspace.id == owner_id).values(id=owner_id)
    )
    if result.rowcount != 1:
        raise ValueError("Verified workspace unavailable")


def prepare_observation(db, owner_id):
    """Hold the owner lock before measurement, until audit commit/rollback.

    Locking only at append time is insufficient: a delayed changed reading
    could otherwise follow a newer unchanged refresh, losing the recovery.
    This lock changes no identity values and controls no financial mutations.
    """
    try:
        connection = db.connection()
        if (
            connection.dialect.name == "sqlite"
            and not connection.connection.driver_connection.in_transaction
        ):
            # SQLite's legacy driver may not BEGIN for SELECTs. Releasing a
            # first SAVEPOINT would then commit the lock before measurement.
            # Establish a real outer transaction, not just SQLAlchemy's logical
            # one, so the operational lock survives until commit/rollback.
            connection.exec_driver_sql("BEGIN IMMEDIATE")
        with db.begin_nested():
            lock_owner(connection, owner_id)
        return True
    except Exception:
        db.rollback()
        return False


def prune(connection, owner_id, now):
    # Global expiration removes safe operational facts only, never financial
    # records. Idle databases are pruned on the next authorized console request.
    cutoff = now - timedelta(days=RETENTION_DAYS)
    connection.execute(delete(TABLE).where(TABLE.c.checked_at < cutoff))
    keep = select(TABLE.c.id).where(TABLE.c.owner_id == owner_id).order_by(
        TABLE.c.id.desc()
    ).limit(MAX_ENTRIES)
    connection.execute(delete(TABLE).where(
        TABLE.c.owner_id == owner_id, TABLE.c.id.not_in(keep),
    ))


def record_observation(db, owner_id, report):
    """Commit only successful evidence; a lost observation is never backfilled."""
    try:
        values = snapshot(report)
        checked_at = datetime.fromisoformat(report["checked_at"])
        if checked_at.tzinfo is None:
            raise ValueError("Observation requires UTC evidence")
        checked_at = utc(checked_at)
        now = datetime.now(timezone.utc)
        if checked_at > now or checked_at < now - timedelta(days=RETENTION_DAYS):
            raise ValueError("Observation outside retention window")
        with db.begin_nested():
            connection = db.connection()
            lock_owner(connection, owner_id)
            prune(connection, owner_id, now)
            previous = connection.execute(select(TABLE).where(
                TABLE.c.owner_id == owner_id,
            ).order_by(TABLE.c.id.desc()).limit(1)).mappings().first()
            recorded = False
            # Do not let a slow older request reverse more recent evidence.
            if previous is None or (
                checked_at > utc(previous["checked_at"])
                and any(previous[key] != values[key] for key in VOCABULARY)
            ):
                connection.execute(insert(TABLE).values(
                    owner_id=owner_id, checked_at=checked_at,
                    kind="BASELINE" if previous is None else "TRANSITION", **values,
                ))
                recorded = True
                prune(connection, owner_id, now)
        db.commit()
        return {"status": "AVAILABLE", "recorded": recorded}
    except Exception:
        db.rollback()
        return {"status": "UNAVAILABLE", "recorded": False}


def history(db, owner_id):
    result = {
        "status": "UNAVAILABLE", "retention_days": RETENTION_DAYS,
        "max_entries": MAX_ENTRIES, "entries": [],
    }
    try:
        with db.begin_nested():
            connection = db.connection()
            lock_owner(connection, owner_id)
            prune(connection, owner_id, datetime.now(timezone.utc))
            rows = connection.execute(select(TABLE).where(
                TABLE.c.owner_id == owner_id,
            ).order_by(TABLE.c.id.desc()).limit(MAX_ENTRIES)).mappings().all()
            entries = []
            for row in rows:
                # Treat damaged or unrecognized stored evidence as unavailable,
                # not an opportunity to echo arbitrary text from the database.
                validate(row)
                if row["kind"] not in {"BASELINE", "TRANSITION"}:
                    raise ValueError("Invalid evidence kind")
                entries.append({
                    "kind": row["kind"], "checked_at": utc(row["checked_at"]).isoformat(),
                    **{key: row[key] for key in VOCABULARY},
                })
        db.commit()
        result.update(status="AVAILABLE", entries=entries)
    except Exception:
        db.rollback()
    return result