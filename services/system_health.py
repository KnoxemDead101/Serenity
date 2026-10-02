"""A bounded runtime observation, not a certification of all Serenity data.

Only schema metadata and zero-row SELECTs are inspected. No financial records,
owner identifiers, credentials, database locations, or raw exceptions leave
this service. Managed Publish need not maintain an Alembic version row.
"""

from datetime import datetime, timezone
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import false, inspect, select, text

from services.write_safety import MESSAGE, write_state
from storage.database import Base


def check(key, label, status, message):
    return {"key": key, "label": label, "status": status, "message": message}


def migration_observation(connection):
    """Allowlist revision labels; an absent tracking row is not missing data."""
    unavailable = {
        "status": "UNVERIFIED", "expected_revision": None,
        "observed_revision": None,
        "message": (
            "Migration tracking could not be verified. Managed Publish applies "
            "schema independently; this is not proof of a missing or empty database."
        ),
    }
    try:
        root = Path(__file__).resolve().parents[1]
        config = Config()
        config.set_main_option("script_location", str(root / "migrations"))
        scripts = ScriptDirectory.from_config(config)
        expected = scripts.get_current_head()
        unavailable["expected_revision"] = expected
        known = {item.revision for item in scripts.walk_revisions()}
        # Optional inspection must not poison the health transaction on PG.
        with connection.begin_nested():
            if not inspect(connection).has_table("alembic_version"):
                return unavailable
            rows = connection.execute(text(
                "SELECT version_num FROM alembic_version LIMIT 2"
            )).scalars().all()
        if len(rows) != 1 or rows[0] not in known:
            return unavailable
        current = rows[0] == expected
        return {
            "status": "CURRENT" if current else "BEHIND",
            "expected_revision": expected, "observed_revision": rows[0],
            "message": (
                "The recorded revision matches this application's migration head. "
                "This does not verify every constraint or Publish approval."
                if current else
                "The recorded revision is behind this application's migration head. "
                "Review schema separately; never repair it from this console."
            ),
        }
    except Exception:
        return unavailable


def system_health(db, *, application_version):
    """Called only after verified workspace authorization; never accepts an owner."""
    checks = [
        check("database", "Database connection", "UNAVAILABLE",
              "Database reachability could not be verified."),
        check("schema", "Readable application schema", "UNAVAILABLE",
              "Required data cannot be verified. Unknown does not mean empty."),
        check("write_safety", "Financial write safety", "UNAVAILABLE",
              "Write safety could not be verified. Do not assume writes are safe."),
    ]
    migration = {
        "status": "UNVERIFIED", "expected_revision": None,
        "observed_revision": None,
        "message": "Migration tracking could not be observed.",
    }
    state = "UNAVAILABLE"
    message = "Reliable application data is unavailable. Unknown does not mean empty."
    try:
        connection = db.connection()
        connection.execute(text("SELECT 1"))
        checks[0] = check(
            "database", "Database connection", "AVAILABLE",
            "This request reached the configured runtime database. No records were read.",
        )
        inspector = inspect(connection)
        # Model-driven coverage includes every loaded domain, not merely Goals.
        # Query zero rows to verify column visibility and SELECT permission too.
        for table in Base.metadata.sorted_tables:
            # Optional operational history must not redefine financial health.
            if table.name in {"system_observations", "manual_verifications"}:
                continue
            if not inspector.has_table(table.name):
                raise RuntimeError("Required schema unavailable")
            actual_columns = {column["name"] for column in inspector.get_columns(table.name)}
            if not set(table.columns.keys()).issubset(actual_columns):
                raise RuntimeError("Required schema unavailable")
            connection.execute(select(*table.columns).where(false()))
        checks[1] = check(
            "schema", "Readable application schema", "AVAILABLE",
            "Required tables and columns are readable through zero-row checks. "
            "Record completeness, balances, freshness, and all constraints are not audited.",
        )
        safety = write_state(connection)
        state = "NORMAL" if safety == "NORMAL" else "READ_ONLY"
        checks[2] = check(
            "write_safety", "Financial write safety",
            "AVAILABLE" if state == "NORMAL" else "READ_ONLY",
            "The existing write guard permits writes at this check. "
            "Each write is checked again; this is not an authorization token."
            if state == "NORMAL" else MESSAGE,
        )
        migration = migration_observation(connection)
        message = (
            "Runtime schema is readable and the existing write guard permits writes. "
            "NORMAL does not certify backups, live feeds, or complete financial data."
            if state == "NORMAL" else
            "Schema reads are available, but the existing safety guard blocks writes. "
            "Do not use this console to bypass publishing protections."
        )
    except Exception:
        # Database exceptions can contain private SQL parameters or locations.
        # Return fixed public messages, never the exception or synthetic totals.
        pass
    checks.extend([
        check("authentication", "Authentication", "AVAILABLE",
              "This request passed Serenity's session and workspace authorization. "
              "This does not verify published sign-in or provider-wide availability."),
        check("backups", "Backup and recovery evidence", "UNVERIFIED",
              "Disposable restore rehearsal exists. Automated off-host backups and "
              "recovery on the intended host are not verified by this check."),
        check("market_data", "Financial and market data provenance", "MANUAL",
              "Existing financial inputs and investment starting positions are manual. "
              "Reference instruments are not live quotes. No verified live market feed "
              "or broker execution is provided by this baseline."),
    ])
    return {
        "state": state, "writes_enabled": state == "NORMAL",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "application_version": application_version,
        "message": message, "checks": checks, "migration": migration,
    }