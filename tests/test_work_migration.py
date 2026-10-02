"""Work migrations are additive and preserve all populated work on downgrade."""

import sqlite3

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from test_goal_composition_migration import _alembic as sqlite_alembic
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401
from test_work import create, goal, ROOT


def test_sqlite_additive_migration_and_empty_downgrade(tmp_path):
    path = tmp_path / "work.db"
    result = sqlite_alembic(path, "upgrade", "0024_restore_publish_keys")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        old_tables = set(row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))
        connection.execute(
            "INSERT INTO accounts (owner_id,name,account_type,classification,"
            "opening_balance_cents,active,created_at,updated_at) "
            "VALUES ('owner-a','Preserved','Checking','Personal',23456,1,"
            "CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
    result = sqlite_alembic(path, "upgrade", "0025_projects_tasks")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        tables = set(row[0] for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ))
        assert tables - old_tables == {"projects", "tasks"}
        assert connection.execute("SELECT opening_balance_cents FROM accounts").fetchone() == (23456,)
    result = sqlite_alembic(path, "downgrade", "0024_restore_publish_keys")
    assert result.returncode == 0, result.stderr
    assert sqlite_alembic(path, "upgrade", "0025_projects_tasks").returncode == 0


@pytest.mark.parametrize("table", ["projects", "tasks"])
def test_sqlite_populated_work_prevents_any_downgrade_drop(tmp_path, table):
    path = tmp_path / "preserve-work.db"
    assert sqlite_alembic(path, "upgrade", "0025_projects_tasks").returncode == 0
    with sqlite3.connect(path) as connection:
        connection.execute(
            f"INSERT INTO {table} (owner_id,name,active,created_at,updated_at) "
            "VALUES ('owner-a','Archive is still data',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
    result = sqlite_alembic(path, "downgrade", "0024_restore_publish_keys")
    assert result.returncode != 0
    assert "Cannot downgrade while Projects or Tasks exist" in result.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute(f"SELECT name FROM {table}").fetchone() == ("Archive is still data",)
        for name in ["projects", "tasks"]:
            connection.execute(f"SELECT * FROM {name}").fetchall()
        assert connection.execute("SELECT version_num FROM alembic_version").fetchone() == ("0025_projects_tasks",)


def test_migrated_sqlite_guards_optional_links_without_enabling_foreign_keys(tmp_path):
    path = tmp_path / "sqlite-guards.db"
    result = sqlite_alembic(path, "upgrade", "head")
    assert result.returncode == 0, result.stderr
    with sqlite3.connect(path) as connection:
        assert connection.execute("PRAGMA foreign_keys").fetchone() == (0,)
        connection.execute(
            "INSERT INTO projects (owner_id,name,created_at,updated_at) "
            "VALUES ('owner-a','Standalone',CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)"
        )
        project_id = connection.execute("SELECT id FROM projects").fetchone()[0]
        for statement in [
            "INSERT INTO projects (owner_id,name,goal_id,created_at,updated_at) "
            "VALUES ('owner-a','Missing',99999,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
            f"INSERT INTO tasks (owner_id,name,project_id,created_at,updated_at) "
            f"VALUES ('other-owner','Foreign',{project_id},CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)",
        ]:
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(statement)
        connection.execute(
            "INSERT INTO tasks (owner_id,name,project_id,created_at,updated_at) "
            "VALUES ('owner-a','Linked',?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)", (project_id,),
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("DELETE FROM projects")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE projects SET owner_id='other'")


@pytest.mark.parametrize("table,parent,link", [
    ("projects", "goals", "goal_id"), ("tasks", "projects", "project_id"),
])
def test_postgres_work_relationship_constraints_and_lifecycle(postgres_url, pg_engine, pg_client, table, parent, link):
    _alembic(postgres_url, "upgrade", "head")
    source = goal(pg_client) if parent == "goals" else create(pg_client, "projects")
    record = create(pg_client, table, **{link: source["id"]})
    foreign_keys = inspect(pg_engine).get_foreign_keys(table)
    assert any(
        fk["constrained_columns"] == ["owner_id", link]
        and fk["referred_table"] == parent
        and fk["referred_columns"] == ["owner_id", "id"]
        and fk["options"]["ondelete"] == "RESTRICT"
        for fk in foreign_keys
    )
    for statement, record_id in [
        (f"UPDATE {table} SET owner_id='other' WHERE id=:id", record["id"]),
        (f"UPDATE {table} SET {link}=999999 WHERE id=:id", record["id"]),
        (f"UPDATE {parent} SET owner_id='other' WHERE id=:id", source["id"]),
        (f"DELETE FROM {parent} WHERE id=:id", source["id"]),
        (f"UPDATE {table} SET status='COMPLETED', completed_at=NULL WHERE id=:id", record["id"]),
    ]:
        with pytest.raises(IntegrityError):
            with pg_engine.begin() as connection:
                connection.execute(text(statement), {"id": record_id})
    assert pg_client.post(f"{ROOT}/{table}/{record['id']}/status", json={"status": "COMPLETED"}).status_code == 200
    refused = _alembic(postgres_url, "downgrade", "0024_restore_publish_keys", succeeds=False)
    assert "Cannot downgrade while Projects or Tasks exist" in refused.stderr
    assert {"projects", "tasks"} <= set(inspect(pg_engine).get_table_names())


def test_postgres_work_read_models_and_exports_do_not_change_finances(postgres_url, pg_engine, pg_client):
    _alembic(postgres_url, "upgrade", "head")
    summary = pg_client.get(ROOT + "/dashboard/summary").json()
    source = goal(pg_client)
    project = create(pg_client, "projects", goal_id=source["id"])
    task = create(pg_client, "tasks", project_id=project["id"])
    changed = pg_client.post(f"{ROOT}/tasks/{task['id']}/status", json={"status": "COMPLETED"})
    assert changed.status_code == 200, changed.text
    assert changed.json()["completed_at"].endswith("Z")
    assert pg_client.get(ROOT + "/dashboard/summary").json() == summary
    assert pg_client.get(f"{ROOT}/goals/{source['id']}").json() == source
    assert pg_client.get(ROOT + "/export").json()["tasks"]