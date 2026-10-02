"""Real permission errors and concurrent audit writes on disposable PostgreSQL."""

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
import threading
import time

import pytest
from sqlalchemy import event, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from services import system_health, system_history
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url, OWNER  # noqa: F401
from test_system_history import evidence


@pytest.fixture(autouse=True)
def migrated(postgres_url, pg_engine):
    assert "/isolated-money-pg" in postgres_url
    with pg_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    _alembic(postgres_url, "upgrade", "head")
    with pg_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO users (id,active,created_at) VALUES ('audit-user',true,CURRENT_TIMESTAMP)"
        ))
        connection.execute(text(
            "INSERT INTO workspaces (id,owner_user_id,name,created_at) "
            "VALUES (:owner,'audit-user','Synthetic',CURRENT_TIMESTAMP)"
        ), {"owner": OWNER})


def test_concurrent_identical_observations_create_one_baseline(pg_engine):
    # Each worker gets a real separate connection/session. A shared workspace
    # lock serializes compare/append even when all observations race.
    now = datetime.now(timezone.utc) - timedelta(seconds=1)

    def record(i):
        with Session(pg_engine) as db:
            return system_history.record_observation(
                db, OWNER, evidence(when=now + timedelta(milliseconds=i)),
            )

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(record, range(8)))
    assert all(r["status"] == "AVAILABLE" for r in results)
    assert sum(r["recorded"] for r in results) == 1
    with Session(pg_engine) as db:
        assert len(system_history.history(db, OWNER)["entries"]) == 1


def test_console_serializes_measurement_not_just_append(pg_client, monkeypatch):
    active = 0
    maximum = 0
    calls = 0
    guard = threading.Lock()

    def observed_safety(connection):
        nonlocal active, maximum, calls
        with guard:
            active += 1
            maximum = max(maximum, active)
            index = calls
            calls += 1
        time.sleep(0.03)
        with guard:
            active -= 1
        return "NORMAL" if index % 2 == 0 else "READ_ONLY"

    monkeypatch.setattr(system_health, "write_state", observed_safety)
    with ThreadPoolExecutor(max_workers=5) as pool:
        reports = list(pool.map(
            lambda _: pg_client.get("/serenity-api/system/health").json(), range(5),
        ))
    assert maximum == 1
    assert all(report["history"]["recorded"] for report in reports)
    entries = pg_client.get("/serenity-api/system/history").json()["entries"]
    assert [entry["state"] for entry in entries] == [
        "NORMAL", "READ_ONLY", "NORMAL", "READ_ONLY", "NORMAL",
    ]


def test_read_only_audit_is_not_a_financial_guard_bypass(postgres_url, pg_engine, pg_client):
    from migrations.publish_key_references import REFERENCES

    table, name, *_ = REFERENCES[0]
    with pg_engine.begin() as connection:
        connection.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{name}"'))
    response = pg_client.get("/serenity-api/system/health").json()
    assert response["state"] == "READ_ONLY"
    assert response["history"] == {"status": "AVAILABLE", "recorded": True}
    assert pg_client.post("/serenity-api/portfolios", json={"name": "Blocked"}).status_code == 503
    assert pg_client.get("/serenity-api/system/history").json()["entries"][0]["state"] == "READ_ONLY"


def test_database_sql_failure_is_rolled_back_before_unavailable_evidence(pg_engine, pg_client):
    def denied(connection, cursor, statement, parameters, context, executemany):
        # PostgreSQL itself aborts the savepoint, not just a Python mock.
        if statement.startswith("SELECT goals."):
            cursor.execute("SELECT missing_private_schema_function()")

    event.listen(pg_engine, "before_cursor_execute", denied)
    try:
        response = pg_client.get("/serenity-api/system/health")
    finally:
        event.remove(pg_engine, "before_cursor_execute", denied)
    assert response.status_code == 200
    assert response.json()["state"] == "UNAVAILABLE"
    assert response.json()["history"]["recorded"]
    assert "missing_private" not in response.text
    assert pg_client.get("/serenity-api/system/history").json()["entries"][0]["state"] == "UNAVAILABLE"
    assert pg_client.get("/serenity-api/system/health").json()["history"]["recorded"]


@pytest.mark.parametrize("permission", ["SELECT", "INSERT"])
def test_audit_permission_failure_is_fixed_and_leaves_schema_reads_valid(pg_engine, permission):
    role = "audit_" + permission.lower()
    with pg_engine.begin() as connection:
        connection.execute(text(f"CREATE ROLE {role} NOLOGIN"))
        connection.execute(text(f"GRANT USAGE ON SCHEMA public TO {role}"))
        connection.execute(text(f"GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO {role}"))
        connection.execute(text(f"GRANT USAGE ON ALL SEQUENCES IN SCHEMA public TO {role}"))
        connection.execute(text(f"REVOKE {permission} ON system_observations FROM {role}"))
    with Session(pg_engine) as db:
        db.execute(text(f"SET ROLE {role}"))
        report = system_health.system_health(db, application_version="test")
        assert report["state"] == "NORMAL"
        assert system_history.record_observation(db, OWNER, report) == {
            "status": "UNAVAILABLE", "recorded": False,
        }
        db.execute(text(f"SET ROLE {role}"))
        result = system_history.history(db, OWNER)
        assert result["entries"] == []
        assert result["status"] == ("UNAVAILABLE" if permission == "SELECT" else "AVAILABLE")
        db.execute(text("RESET ROLE"))
        db.commit()
    with pg_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM system_observations")) == 0


def test_migration_fk_vocabulary_and_populated_downgrade_preservation(postgres_url, pg_engine):
    fk = inspect(pg_engine).get_foreign_keys("system_observations")[0]
    assert fk["referred_table"] == "workspaces"
    assert fk["referred_columns"] == ["id"]
    assert fk["options"]["ondelete"] == "CASCADE"
    with Session(pg_engine) as db:
        assert system_history.record_observation(db, OWNER, evidence())["recorded"]
    for statement in (
        "UPDATE system_observations SET owner_id='missing-owner'",
        "UPDATE system_observations SET migration='PRIVATE'",
    ):
        with pytest.raises(IntegrityError):
            with pg_engine.begin() as connection:
                connection.execute(text(statement))
    refused = _alembic(postgres_url, "downgrade", "0025_projects_tasks", succeeds=False)
    assert "Cannot downgrade while operational history exists" in refused.stderr
    with pg_engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM system_observations")) == 1