"""The opt-in production report never connects or treats missing data as empty."""

import csv
from datetime import datetime, timedelta, timezone
import io
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest
from sqlalchemy import text

from models.goal import Goal
from storage.goals_schema_readiness import (
    FIELDS, METADATA_SQL, REQUIRED_COLUMNS, evaluate_metadata,
)
from test_money_postgres import pg_engine, postgres_url  # noqa: F401

NOW = datetime(2026, 10, 2, tzinfo=timezone.utc)
SCRIPT = Path(__file__).resolve().parents[1] / "scripts/check_goals_schema.py"


def snapshot(*, replica=True, exists=True, visible=True, missing=(), hidden=()):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(FIELDS)
    writer.writerow((
        "t" if replica else "f", "t" if exists else "f",
        "t" if visible else "f", "|".join(missing), "|".join(hidden),
    ))
    return {
        "environment": "production", "target": "replit_database",
        "checked_at": NOW.isoformat(),
        "result": {"success": True, "exitCode": 0, "output": output.getvalue()},
    }


def test_required_columns_cover_entire_goal_model():
    assert set(REQUIRED_COLUMNS) == set(Goal.__table__.columns.keys())


@pytest.mark.parametrize("replica", [True, False])
def test_ready_is_only_schema_observation(replica):
    code, message = evaluate_metadata(snapshot(replica=replica), now=NOW)
    assert code == 0
    assert "READY (schema only)" in message
    assert "No Goal rows read" in message
    assert "not live-primary/runtime, constraint, sign-in" in message
    assert ("replica" in message) == replica


def test_missing_table_is_unknown_not_empty_and_lag_is_explicit():
    code, message = evaluate_metadata(snapshot(
        exists=False, visible=False, missing=REQUIRED_COLUMNS,
        hidden=REQUIRED_COLUMNS,
    ), now=NOW)
    assert code == 1
    assert "public.goals table" in message
    assert "repeat with fresh metadata" in message
    assert "does not prove absence on the live primary" in message
    assert "unknown, not empty" in message


def test_missing_column_and_visibility_failure_are_distinct():
    absent = ("current_progress_amount_cents",)
    code, message = evaluate_metadata(
        snapshot(missing=absent, hidden=absent), now=NOW,
    )
    assert code == 1
    assert absent[0] in message
    code, message = evaluate_metadata(snapshot(hidden=absent), now=NOW)
    assert code == 2
    assert "exist in the catalog" in message
    assert "Do not bypass access controls" in message


@pytest.mark.parametrize("change", [
    {"environment": "development"},
    {"target": "external_database"},
    {"checked_at": (NOW - timedelta(minutes=6)).isoformat()},
    {"checked_at": (NOW + timedelta(seconds=1)).isoformat()},
    {"checked_at": NOW.replace(tzinfo=None).isoformat()},
    {"checked_at": "invalid"},
    {"result": {"success": False, "exitCode": 1, "output": "private-credential"}},
    {"result": {"success": True, "exitCode": 1, "output": "private-credential"}},
    {"result": {"success": True, "exitCode": 0, "output": "private-record"}},
    {"result": {}},
])
def test_invalid_unavailable_stale_or_wrong_target_is_redacted(change):
    data = snapshot()
    data.update(change)
    code, message = evaluate_metadata(data, now=NOW)
    assert code == 2
    assert "UNAVAILABLE" in message
    assert "private" not in message


@pytest.mark.parametrize("data", [None, [], {}, {"result": None}])
def test_malformed_envelope_fails_closed(data):
    assert evaluate_metadata(data, now=NOW)[0] == 2


def test_unexpected_columns_duplicate_rows_and_inconsistent_evidence_fail_closed():
    for data in (
        snapshot(missing=("private-record",), hidden=("private-record",)),
        snapshot(missing=("id",), hidden=()),
        snapshot(exists=False),
        snapshot(missing=("id", "id"), hidden=("id",)),
    ):
        code, message = evaluate_metadata(data, now=NOW)
        assert code == 2
        assert "private-record" not in message
    data = snapshot()
    data["result"]["output"] += data["result"]["output"].splitlines()[1] + "\n"
    assert evaluate_metadata(data, now=NOW)[0] == 2


def test_fresh_retry_can_be_ready_but_saved_success_expires():
    blocked = snapshot(missing=("id",), hidden=("id",))
    assert evaluate_metadata(blocked, now=NOW)[0] == 1
    fresh = snapshot()
    assert evaluate_metadata(fresh, now=NOW)[0] == 0
    assert evaluate_metadata(fresh, now=NOW + timedelta(minutes=6))[0] == 2


def test_cli_requires_opt_in_and_ignores_inherited_database_settings():
    env = {**os.environ, "DATABASE_URL": "not-a-database-url",
           "SERENITY_CHECK_DATABASE_URL": "not-a-database-url"}
    query = subprocess.run(
        [sys.executable, str(SCRIPT), "--print-query"], env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert query.returncode == 0
    assert query.stdout.strip() == METADATA_SQL.strip()
    no_flag = subprocess.run(
        [sys.executable, str(SCRIPT)], env=env,
        capture_output=True, text=True, timeout=10,
    )
    assert no_flag.returncode == 2
    data = snapshot()
    data["checked_at"] = datetime.now(timezone.utc).isoformat()
    for payload, expected in (
        (json.dumps(data), 0), ("private-credential", 2), ("x" * 65537, 2),
    ):
        report = subprocess.run(
            [sys.executable, str(SCRIPT), "--production-metadata"], env=env,
            input=payload, capture_output=True, text=True, timeout=10,
        )
        assert report.returncode == expected
        assert "private-credential" not in report.stdout + report.stderr
        assert not report.stderr


def test_query_on_disposable_postgres_missing_partial_empty_populated_and_hidden(pg_engine):
    """Real query validation on a private cluster, never on managed production."""
    def observe(connection):
        result = connection.execute(text(METADATA_SQL)).mappings().one()
        data = snapshot(
            replica=result["is_replica"], exists=result["table_exists"],
            visible=result["table_visible"],
            missing=result["missing_columns"].split("|") if result["missing_columns"] else (),
            hidden=result["unavailable_columns"].split("|") if result["unavailable_columns"] else (),
        )
        return evaluate_metadata(data, now=NOW)

    with pg_engine.begin() as connection:
        assert observe(connection)[0] == 1
        connection.execute(text("CREATE TABLE public.goals (id integer)"))
        assert observe(connection)[0] == 1
        for name in REQUIRED_COLUMNS:
            if name != "id":
                connection.execute(text(f"ALTER TABLE public.goals ADD COLUMN {name} text"))
        empty = observe(connection)
        assert empty[0] == 0
        connection.execute(text("INSERT INTO public.goals (id, name) VALUES (1, 'sentinel')"))
        assert observe(connection) == empty  # Data presence is never reported.
        connection.execute(text("CREATE ROLE metadata_only NOLOGIN"))
        connection.execute(text("SET LOCAL ROLE metadata_only"))
        assert observe(connection)[0] == 2  # Catalog present; privileges hidden.
        connection.execute(text("RESET ROLE"))
        connection.execute(text("GRANT UPDATE ON public.goals TO metadata_only"))
        connection.execute(text("SET LOCAL ROLE metadata_only"))
        # Visible metadata, but no SELECT privilege on Goals: query still succeeds.
        assert observe(connection)[0] == 0
        connection.execute(text("RESET ROLE"))
        connection.execute(text("DROP TABLE public.goals"))
        connection.execute(text("DROP ROLE metadata_only"))