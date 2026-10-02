"""Offline evaluation of managed-production metadata; never opens a database.

The caller must obtain fresh metadata through Replit's production read-only
tool. Neither the app engine nor caller-selected database URLs are used here.
"""

import csv
from datetime import datetime, timedelta, timezone
import io

REQUIRED_COLUMNS = (
    "id", "owner_id", "name", "description", "goal_type", "category", "status",
    "priority", "target_date", "target_amount_cents", "progress_source",
    "current_progress_amount_cents", "notes", "active", "completed_at",
    "created_at", "updated_at",
)
MAX_AGE = timedelta(minutes=5)

# Fixed identifiers only. No application table is read, even when it exists.
# Catalogs distinguish missing objects from information_schema visibility.
METADATA_SQL = """
WITH required(column_name) AS (
    VALUES
        """ + ",\n        ".join(f"('{name}')" for name in REQUIRED_COLUMNS) + """
), goal_table AS (
    SELECT c.oid
    FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid = c.relnamespace
    WHERE n.nspname = 'public' AND c.relname = 'goals'
      AND c.relkind IN ('r', 'p')
)
SELECT
    pg_is_in_recovery() AS is_replica,
    EXISTS (SELECT 1 FROM goal_table) AS table_exists,
    EXISTS (
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = 'public' AND table_name = 'goals'
          AND table_type = 'BASE TABLE'
    ) AS table_visible,
    COALESCE((
        SELECT string_agg(r.column_name, '|' ORDER BY r.column_name)
        FROM required r
        WHERE NOT EXISTS (
            SELECT 1 FROM pg_catalog.pg_attribute a
            JOIN goal_table g ON g.oid = a.attrelid
            WHERE a.attname = r.column_name
              AND a.attnum > 0 AND NOT a.attisdropped
        )
    ), '') AS missing_columns,
    COALESCE((
        SELECT string_agg(r.column_name, '|' ORDER BY r.column_name)
        FROM required r
        WHERE NOT EXISTS (
            SELECT 1 FROM information_schema.columns c
            WHERE c.table_schema = 'public' AND c.table_name = 'goals'
              AND c.column_name = r.column_name
        )
    ), '') AS unavailable_columns
"""

FIELDS = ("is_replica", "table_exists", "table_visible",
          "missing_columns", "unavailable_columns")


def evaluate_metadata(snapshot, *, now=None):
    """Return a safe message and exit code: ready=0, missing=1, unavailable=2.

    Snapshot provenance is an operator assertion, not cryptographic evidence.
    A replica success proves only column presence/visibility at observation time.
    All errors are redacted; tool output and unknown identifiers never print.
    """
    unavailable = (2, "UNAVAILABLE: fresh managed-production metadata could not "
                   "be verified. Goals data is unknown, not empty.")
    now = now or datetime.now(timezone.utc)
    try:
        if (snapshot["environment"] != "production"
                or snapshot["target"] != "replit_database"):
            return unavailable
        checked_at = datetime.fromisoformat(snapshot["checked_at"])
        if checked_at.tzinfo is None or not timedelta(0) <= now - checked_at <= MAX_AGE:
            return unavailable
        result = snapshot["result"]
        if result["success"] is not True or result["exitCode"] != 0:
            return unavailable
        reader = csv.DictReader(io.StringIO(result["output"]), strict=True)
        if tuple(reader.fieldnames or ()) != FIELDS:
            return unavailable
        rows = list(reader)
        if len(rows) != 1 or set(rows[0]) != set(FIELDS):
            return unavailable
        row = rows[0]
        if any(row[key] not in ("t", "f") for key in FIELDS[:3]):
            return unavailable
        missing = row["missing_columns"].split("|") if row["missing_columns"] else []
        hidden = row["unavailable_columns"].split("|") if row["unavailable_columns"] else []
        if (not set(missing + hidden) <= set(REQUIRED_COLUMNS)
                or len(set(missing)) != len(missing)
                or len(set(hidden)) != len(hidden)
                or not set(missing) <= set(hidden)):
            return unavailable
        exists = row["table_exists"] == "t"
        visible = row["table_visible"] == "t"
        replica = row["is_replica"] == "t"
        if not exists and (visible or set(missing) != set(REQUIRED_COLUMNS)):
            return unavailable
        scope = "production read-only replica" if replica else "production read-only connection"
        if not exists or missing:
            detail = ("public.goals table" if not exists else
                      "required columns: " + ", ".join(sorted(missing)))
            message = f"MISSING: {detail} not present in the {scope}. Not ready."
            if replica:
                message += (" Allow replica catch-up and repeat with fresh metadata; "
                            "this does not prove absence on the live primary.")
            return 1, message + " Goals data is unknown, not empty."
        if not visible or hidden:
            return 2, ("UNAVAILABLE: Goals objects exist in the catalog but required "
                       "metadata is not fully visible. Not ready; Goals data is "
                       "unknown, not empty. Do not bypass access controls.")
        return 0, (f"READY (schema only): public.goals and all required columns "
                   f"are present and visible in the {scope}. No Goal rows read. "
                   "This is not live-primary/runtime, constraint, sign-in, "
                   "data-safety, or backup verification.")
    except (KeyError, TypeError, ValueError, csv.Error, OverflowError):
        return unavailable