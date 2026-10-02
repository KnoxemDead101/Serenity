"""Operational audit evidence uses synthetic workspaces and disposable storage."""

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from sqlalchemy import create_engine, event, func, select, text
from sqlalchemy.orm import Session

from models.identity import SerenityUser, Workspace
from models.system_observation import SystemObservation
from services import system_health, system_history
from tests.conftest import sign_in_as, TEST_CLERK_ISSUER
from services.identity_service import CLERK_PROVIDER, workspace_for_identity
from storage.database import Base
from test_goal_composition_migration import _alembic as sqlite_alembic

HEALTH = "/serenity-api/system/health"
HISTORY = "/serenity-api/system/history"


def workspace(db, owner_id="test-owner"):
    db.add(SerenityUser(id="user-" + owner_id))
    db.add(Workspace(id=owner_id, owner_user_id="user-" + owner_id, name="Synthetic"))
    db.commit()
    return owner_id


def count(db):
    return db.scalar(select(func.count()).select_from(SystemObservation))


def evidence(*, state="NORMAL", when=None, migration="UNVERIFIED"):
    when = when or datetime.now(timezone.utc)
    return {
        "state": state, "checked_at": when.isoformat(),
        "checks": [
            {"key": "database", "status": "AVAILABLE"},
            {"key": "schema", "status": "AVAILABLE" if state != "UNAVAILABLE" else "UNAVAILABLE"},
            {"key": "write_safety", "status": {
                "NORMAL": "AVAILABLE", "READ_ONLY": "READ_ONLY", "UNAVAILABLE": "UNAVAILABLE",
            }[state]},
        ],
        "migration": {"status": migration},
        "private": "secret-location-financial-value-raw-exception",
    }


def test_first_observation_repeats_transitions_and_utc_evidence(client, db, monkeypatch):
    workspace(db)
    first = client.get(HEALTH).json()
    assert first["history"] == {"status": "AVAILABLE", "recorded": True}
    assert count(db) == 1
    repeat = client.get(HEALTH).json()
    assert repeat["history"] == {"status": "AVAILABLE", "recorded": False}
    assert count(db) == 1
    monkeypatch.setattr(system_health, "write_state", lambda connection: "READ_ONLY")
    changed = client.get(HEALTH).json()
    assert changed["history"]["recorded"]
    assert client.get(HEALTH).json()["history"]["recorded"] is False
    monkeypatch.setattr(system_health, "write_state", lambda connection: "NORMAL")
    restored = client.get(HEALTH).json()
    result = client.get(HISTORY)
    assert result.headers["cache-control"] == "no-store"
    entries = result.json()["entries"]
    assert [e["state"] for e in entries] == ["NORMAL", "READ_ONLY", "NORMAL"]
    assert [e["kind"] for e in entries] == ["TRANSITION", "TRANSITION", "BASELINE"]
    assert [e["checked_at"] for e in entries] == [
        restored["checked_at"], changed["checked_at"], first["checked_at"],
    ]
    assert count(db) == 3  # Reading history is not a new observation.


def test_subsystem_change_without_overall_state_and_redaction(db):
    owner = workspace(db)
    first = evidence()
    first["application_version"] = "private-version-string"
    first["data_health"] = {"amount": 123456, "record_count": 99, "name": "private-name"}
    assert system_history.record_observation(db, owner, first)["recorded"]
    changed = evidence(migration="CURRENT")
    assert system_history.record_observation(db, owner, changed)["recorded"]
    result = system_history.history(db, owner)
    assert len(result["entries"]) == 2
    assert all(e["state"] == "NORMAL" for e in result["entries"])
    public = json.dumps(result)
    for private in (owner, "private", "123456", "record_count", "application_version"):
        assert private not in public
    columns = set(SystemObservation.__table__.columns.keys())
    assert columns == {"id", "owner_id", "checked_at", "kind", *system_history.VOCABULARY}
    before = count(db)
    invalid = evidence()
    invalid["checks"][0]["status"] = "private-database-location"
    assert system_history.record_observation(db, owner, invalid)["status"] == "UNAVAILABLE"
    assert count(db) == before
    assert "private" not in json.dumps(system_history.history(db, owner))


def test_missing_domain_records_unavailable_then_recovery(client, db):
    workspace(db)
    assert client.get(HEALTH).json()["state"] == "NORMAL"
    db.execute(text("ALTER TABLE goals RENAME COLUMN name TO hidden_name"))
    db.commit()
    report = client.get(HEALTH).json()
    assert report["state"] == "UNAVAILABLE"
    assert report["history"]["recorded"]
    db.execute(text("ALTER TABLE goals RENAME COLUMN hidden_name TO name"))
    db.commit()
    assert client.get(HEALTH).json()["history"]["recorded"]
    assert [e["state"] for e in client.get(HISTORY).json()["entries"]] == [
        "NORMAL", "UNAVAILABLE", "NORMAL",
    ]


@pytest.mark.parametrize("failure", ["missing", "read", "write"])
def test_history_storage_failure_independent_redacted_and_not_backfilled(client, db, failure):
    workspace(db)
    engine = db.get_bind()
    if failure == "missing":
        db.execute(text("DROP TABLE system_observations"))
        db.commit()

    def denied(connection, cursor, statement, parameters, context, executemany):
        if "system_observations" in statement and (
            (failure == "read" and statement.lstrip().startswith("SELECT"))
            or (failure == "write" and statement.lstrip().startswith("INSERT"))
        ):
            raise RuntimeError("private-error postgresql://credential@location 999999")

    event.listen(engine, "before_cursor_execute", denied)
    try:
        response = client.get(HEALTH)
        assert response.status_code == 200
        assert response.json()["state"] == "NORMAL"
        assert response.json()["history"] == {"status": "UNAVAILABLE", "recorded": False}
        assert "private-error" not in response.text
        result = client.get(HISTORY).json()
        # Write-only failure may leave readable, truthfully empty history.
        assert result["status"] == ("AVAILABLE" if failure == "write" else "UNAVAILABLE")
        assert result["entries"] == []
    finally:
        event.remove(engine, "before_cursor_execute", denied)
    if failure != "missing":
        assert count(db) == 0
        # Recovery records only the current request, not the failed observation.
        fresh = client.get(HEALTH).json()
        entries = client.get(HISTORY).json()["entries"]
        assert entries[0]["kind"] == "BASELINE"
        assert entries[0]["checked_at"] == fresh["checked_at"]


def test_owner_isolation_anonymous_expired_and_inactive(real_auth_client, db):
    assert real_auth_client.get(HISTORY).status_code == 401
    owners = []
    for subject in ("history-a", "history-b"):
        owners.append(workspace_for_identity(
            db, provider=CLERK_PROVIDER, issuer=TEST_CLERK_ISSUER, subject=subject,
        ))
    system_history.record_observation(db, owners[0], evidence(state="READ_ONLY"))
    system_history.record_observation(db, owners[1], evidence(migration="CURRENT"))
    sign_in_as(real_auth_client, "history-a")
    response = real_auth_client.get(HISTORY + "?owner_id=" + owners[1])
    assert response.json()["entries"][0]["state"] == "READ_ONLY"
    assert len(response.json()["entries"]) == 1
    assert not any(owner in response.text for owner in owners)
    sign_in_as(real_auth_client, "history-b")
    assert real_auth_client.get(HISTORY).json()["entries"][0]["migration"] == "CURRENT"
    user_id = db.scalar(select(Workspace.owner_user_id).where(Workspace.id == owners[1]))
    db.execute(text("UPDATE users SET active=false WHERE id=:id"), {"id": user_id})
    db.commit()
    response = real_auth_client.get(HISTORY)
    assert response.status_code == 403
    assert response.headers["cache-control"] == "no-store"
    assert "entries" not in response.text
    real_auth_client.cookies.set("serenity_session", "expired-or-invalid")
    assert real_auth_client.get(HISTORY).status_code == 401
    assert count(db) == 2


def test_identity_failure_has_no_history_or_new_observation(real_auth_client, db):
    sign_in_as(real_auth_client, "history-unavailable")
    db.execute(text("DROP TABLE auth_identities"))
    db.commit()
    response = real_auth_client.get(HISTORY)
    assert response.status_code == 503
    assert response.headers["cache-control"] == "no-store"
    assert "entries" not in response.text
    assert count(db) == 0


def test_retention_count_age_and_delayed_requests(db):
    owner = workspace(db)
    other = workspace(db, "other-owner")
    now = datetime.now(timezone.utc)
    for i in range(205):
        result = system_history.record_observation(
            db, owner, evidence(
                state="NORMAL" if i % 2 == 0 else "READ_ONLY",
                when=now - timedelta(minutes=210 - i),
            ),
        )
        assert result["recorded"]
    assert count(db) == 200
    latest = system_history.history(db, owner)["entries"][0]
    stale = evidence(state="READ_ONLY", when=now - timedelta(days=1))
    assert system_history.record_observation(db, owner, stale)["recorded"] is False
    assert system_history.history(db, owner)["entries"][0] == latest
    assert system_history.record_observation(db, other, evidence())["recorded"]
    db.execute(text(
        "UPDATE system_observations SET checked_at=:old WHERE owner_id=:owner"
    ), {"old": now - timedelta(days=91), "owner": owner})
    db.commit()
    assert system_history.history(db, other)["status"] == "AVAILABLE"
    assert count(db) == 1  # Global age pruning, no other owner's activity returned.
    assert system_history.history(db, owner)["entries"] == []
    assert system_history.record_observation(db, owner, evidence())["recorded"]
    assert system_history.history(db, owner)["entries"][0]["kind"] == "BASELINE"


def test_sqlite_outer_lock_survives_savepoint_until_observation_commits(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'concurrent.db'}")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as db:
            owner = workspace(db)
        active = 0
        maximum = 0
        guard = threading.Lock()

        def observed(_):
            nonlocal active, maximum
            with Session(engine) as db:
                assert system_history.prepare_observation(db, owner)
                with guard:
                    active += 1
                    maximum = max(maximum, active)
                time.sleep(0.03)
                report = evidence()
                with guard:
                    active -= 1
                return system_history.record_observation(db, owner, report)

        with ThreadPoolExecutor(max_workers=5) as pool:
            results = list(pool.map(observed, range(5)))
        assert maximum == 1
        assert all(result["status"] == "AVAILABLE" for result in results)
        assert sum(result["recorded"] for result in results) == 1
    finally:
        engine.dispose()


def test_sqlite_migration_additive_constraints_and_preservation(tmp_path):
    path = tmp_path / "history.db"
    assert sqlite_alembic(path, "upgrade", "0025_projects_tasks").returncode == 0
    with sqlite3.connect(path) as connection:
        tables_before = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    result = sqlite_alembic(path, "upgrade", "0026_system_observations")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        tables_after = {r[0] for r in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        assert tables_after - tables_before == {"system_observations"}
        connection.execute(
            "INSERT INTO system_observations "
            "(owner_id,checked_at,kind,state,database,schema,write_safety,migration) "
            "VALUES ('synthetic',CURRENT_TIMESTAMP,'BASELINE','NORMAL','AVAILABLE','AVAILABLE','AVAILABLE','CURRENT')"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE system_observations SET state='private-exception'")
    refused = sqlite_alembic(path, "downgrade", "0025_projects_tasks")
    assert refused.returncode != 0
    assert "Cannot downgrade while operational history exists" in refused.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM system_observations").fetchone()[0] == 1
        connection.execute("DELETE FROM system_observations")
    assert sqlite_alembic(path, "downgrade", "0025_projects_tasks").returncode == 0