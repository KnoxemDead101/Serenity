"""Read-only health observations, redaction, and verified-session boundaries."""

import json

import pytest
from sqlalchemy import event, text
from sqlalchemy.exc import OperationalError

from services import system_health
from services.identity_service import CLERK_PROVIDER, workspace_for_identity
from tests.conftest import TEST_CLERK_ISSUER, sign_in_as

PATH = "/serenity-api/system/health"


def test_normal_is_bounded_and_only_reads_owner_scoped_records(client, db):
    statements = []
    engine = db.get_bind()

    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(engine, "before_cursor_execute", capture)
    try:
        response = client.get(PATH)
    finally:
        event.remove(engine, "before_cursor_execute", capture)
    data = response.json()
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert data["state"] == "NORMAL"
    assert data["writes_enabled"] is True
    assert data["checked_at"].endswith("+00:00")
    assert data["application_version"] == "0.2.0"
    checks = {item["key"]: item for item in data["checks"]}
    assert checks["backups"]["status"] == "UNVERIFIED"
    assert checks["market_data"]["status"] == "MANUAL"
    assert "does not verify published sign-in" in checks["authentication"]["message"]
    assert data["migration"]["status"] == "UNVERIFIED"
    # Runtime schema checks return zero rows; Data Health reads scoped inputs.
    for statement in statements:
        if "SELECT" in statement and "FROM accounts" in statement:
            assert "WHERE 0 = 1" in statement or "WHERE accounts.owner_id = ?" in statement
        assert not statement.lstrip().upper().startswith((
            "CREATE", "ALTER", "DROP",
        ))
        if statement.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE")):
            # Only identity locking and the separate bounded operational audit
            # may write during a health request; financial records stay read-only.
            assert "workspaces" in statement or "system_observations" in statement
    assert statements


def test_read_only_uses_existing_guard_without_lock_or_bypass(client, monkeypatch):
    locks = []

    def blocked(connection, *, lock=False):
        locks.append(lock)
        return "READ_ONLY"

    monkeypatch.setattr(system_health, "write_state", blocked)
    data = client.get(PATH).json()
    assert data["state"] == "READ_ONLY"
    assert data["writes_enabled"] is False
    assert locks == [False]
    assert data["checks"][1]["status"] == "AVAILABLE"


@pytest.mark.parametrize("damage", ["table", "column"])
def test_unavailable_schema_is_unknown_not_empty(client, db, damage):
    if damage == "table":
        db.execute(text("DROP TABLE goals"))
    else:
        db.execute(text("ALTER TABLE goals RENAME COLUMN name TO hidden_name"))
    db.commit()
    data = client.get(PATH).json()
    assert data["state"] == "UNAVAILABLE"
    assert not data["writes_enabled"]
    assert data["checks"][0]["status"] == "AVAILABLE"
    assert data["checks"][1]["status"] == "UNAVAILABLE"
    assert "Unknown does not mean empty" in data["message"]
    assert all(r["record_count"] is None for r in data["data_health"]["readings"])


def test_connectivity_failure_is_fixed_redacted_response(client, db, monkeypatch):
    def fail():
        raise OperationalError("secret-host", {"amount": "private-record"}, Exception("token"))

    monkeypatch.setattr(db, "connection", fail)
    response = client.get(PATH)
    assert response.status_code == 200
    assert response.json()["state"] == "UNAVAILABLE"
    for forbidden in ("secret-host", "private-record", "token"):
        assert forbidden not in response.text


def test_guard_probe_failure_never_assumes_normal(client, monkeypatch):
    def fail(connection):
        raise RuntimeError("private-error")

    monkeypatch.setattr(system_health, "write_state", fail)
    response = client.get(PATH)
    assert response.json()["state"] == "UNAVAILABLE"
    assert not response.json()["writes_enabled"]
    assert "private-error" not in response.text


def test_migration_labels_are_allowlisted_not_publish_authority(client, db):
    db.execute(text("CREATE TABLE alembic_version (version_num varchar(64))"))
    db.execute(text("INSERT INTO alembic_version VALUES ('private-record')"))
    db.commit()
    response = client.get(PATH)
    assert response.json()["migration"]["status"] == "UNVERIFIED"
    assert "private-record" not in response.text
    expected = response.json()["migration"]["expected_revision"]
    db.execute(text("UPDATE alembic_version SET version_num=:revision"), {"revision": expected})
    db.commit()
    assert client.get(PATH).json()["migration"]["status"] == "CURRENT"
    db.execute(text("UPDATE alembic_version SET version_num='0018_goal_core'"))
    db.commit()
    data = client.get(PATH).json()
    assert data["migration"]["status"] == "BEHIND"
    # Migration tracking is not the managed Publish schema authority.
    assert data["state"] == "NORMAL"


def test_anonymous_cannot_get_console_or_health(real_auth_client):
    response = real_auth_client.get(PATH)
    assert response.status_code == 401
    assert response.headers["cache-control"] == "no-store"
    response = real_auth_client.get("/system", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"] == "/sign-in?next=/system"
    assert response.headers["cache-control"] == "no-store"


def test_owner_records_and_caller_selected_workspace_are_never_disclosed(real_auth_client, db):
    owners = []
    for subject in ("health-owner-a", "health-owner-b"):
        owners.append(workspace_for_identity(
            db, provider=CLERK_PROVIDER, issuer=TEST_CLERK_ISSUER, subject=subject,
        ))
    # Use ordinary owner-isolated APIs to seed synthetic, not production, data.
    for subject in ("health-owner-a", "health-owner-b"):
        sign_in_as(real_auth_client, subject)
        assert real_auth_client.post("/serenity-api/goals", json={
            "name": f"private-{subject}", "goal_type": "SAVINGS",
            "category": "FINANCIAL", "priority": "NORMAL",
        }).status_code == 201
    outputs = []
    for subject in ("health-owner-a", "health-owner-b"):
        sign_in_as(real_auth_client, subject)
        response = real_auth_client.get(PATH + "?owner_id=" + owners[1])
        assert response.status_code == 200
        assert all(value not in response.text for value in owners)
        assert "private-health" not in response.text
        data = response.json()
        data.pop("checked_at")
        data["data_health"].pop("checked_at")
        outputs.append(data)
    assert outputs[0] == outputs[1]


def test_auth_identity_schema_failure_does_not_disclose_health(real_auth_client, db):
    sign_in_as(real_auth_client, "unknown-owner")
    db.execute(text("DROP TABLE auth_identities"))
    db.commit()
    for path in (PATH, "/system"):
        response = real_auth_client.get(path)
        assert response.status_code == 503
        assert response.json()["code"] == "SERENITY_UNAVAILABLE"
        assert "checks" not in response.json()
        assert "auth_identities" not in response.text
        assert response.headers["cache-control"] == "no-store"