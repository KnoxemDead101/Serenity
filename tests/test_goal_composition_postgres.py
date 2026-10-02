"""Goal Composition PostgreSQL constraints use the disposable private cluster."""

import pytest
from sqlalchemy import inspect, text
from sqlalchemy.exc import IntegrityError

from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401


def _goal(client):
    response = client.post("/serenity-api/goals", json={
        "name": "PostgreSQL composition",
        "goal_type": "SAVINGS",
        "category": "FINANCIAL",
        "target_amount": "100.00",
    })
    assert response.status_code == 201, response.text
    return response.json()


@pytest.mark.parametrize("table", [
    "goal_items", "goal_milestones", "goal_checkpoints",
])
def test_postgres_child_tables_have_bigint_money_owner_fk_and_stable_indexes(
    postgres_url, pg_engine, pg_client, table,
):
    _alembic(postgres_url, "upgrade", "head")
    goal = _goal(pg_client)
    inspector = inspect(pg_engine)
    assert table in inspector.get_table_names()
    columns = {column["name"]: column for column in inspector.get_columns(table)}
    if table == "goal_items":
        money_fields = {"expected_cost_cents", "manual_actual_cost_override_cents"}
    elif table == "goal_checkpoints":
        money_fields = {"amount_cents"}
    else:
        money_fields = set()
    for field in money_fields:
        assert columns[field]["type"].__class__.__name__ == "BIGINT"
    foreign_keys = inspector.get_foreign_keys(table)
    assert any(
        foreign_key["referred_table"] == "goals"
        and foreign_key["constrained_columns"] == ["owner_id", "goal_id"]
        and foreign_key["referred_columns"] == ["owner_id", "id"]
        and foreign_key["options"].get("ondelete") == "RESTRICT"
        for foreign_key in foreign_keys
    )
    indexes = inspector.get_indexes(table)
    assert any(
        index["column_names"] == ["owner_id", "goal_id", "sort_order", "id"]
        for index in indexes
    )

    if table == "goal_items":
        record = pg_client.post(
            f"/serenity-api/goals/{goal['id']}/items",
            json={"name": "Valid owner-scoped item"},
        ).json()
        invalid_insert = text(
            "INSERT INTO goal_items "
            "(owner_id, goal_id, name, status, active, created_at, updated_at) "
            "VALUES ('foreign-owner', :goal_id, 'Invalid owner', 'PLANNED', "
            "true, now(), now())"
        )
    elif table == "goal_milestones":
        record = pg_client.post(
            f"/serenity-api/goals/{goal['id']}/milestones",
            json={"title": "Valid owner-scoped milestone"},
        ).json()
        invalid_insert = text(
            "INSERT INTO goal_milestones "
            "(owner_id, goal_id, title, status, created_at, updated_at) "
            "VALUES ('foreign-owner', :goal_id, 'Invalid owner', "
            "'NOT_STARTED', now(), now())"
        )
    else:
        record = pg_client.post(
            f"/serenity-api/goals/{goal['id']}/checkpoints",
            json={"amount": "1.00"},
        ).json()
        invalid_insert = text(
            "INSERT INTO goal_checkpoints "
            "(owner_id, goal_id, amount_cents, created_at, updated_at) "
            "VALUES ('foreign-owner', :goal_id, 100, now(), now())"
        )
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(invalid_insert, {"goal_id": goal["id"]})
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(
                text(f"UPDATE {table} SET owner_id = 'foreign-owner' WHERE id = :id"),
                {"id": record["id"]},
            )


@pytest.mark.parametrize("table", [
    "goal_items", "goal_milestones", "goal_checkpoints",
])
def test_postgres_composition_downgrade_refuses_each_populated_family_before_any_drop(
    postgres_url, pg_engine, table,
):
    _alembic(postgres_url, "upgrade", "head")
    with pg_engine.begin() as connection:
        connection.execute(text("DELETE FROM goal_items"))
        connection.execute(text("DELETE FROM goal_milestones"))
        connection.execute(text("DELETE FROM goal_checkpoints"))
        connection.execute(text("DELETE FROM goals"))
        goal_id = connection.scalar(text(
            "INSERT INTO goals (owner_id, name, goal_type, category, status, priority, "
            "progress_source, active, created_at, updated_at) "
            "VALUES ('postgres-money-test', 'PG downgrade guard', 'SAVINGS', "
            "'FINANCIAL', 'NOT_STARTED', 'NORMAL', 'MANUAL', true, now(), now()) "
            "RETURNING id"
        ))
        if table == "goal_items":
            connection.execute(text(
                "INSERT INTO goal_items (owner_id, goal_id, name, status, active, "
                "created_at, updated_at) VALUES ('postgres-money-test', :id, "
                "'Retain item', 'PLANNED', true, now(), now())"
            ), {"id": goal_id})
        elif table == "goal_milestones":
            connection.execute(text(
                "INSERT INTO goal_milestones (owner_id, goal_id, title, status, "
                "created_at, updated_at) VALUES ('postgres-money-test', :id, "
                "'Retain milestone', 'NOT_STARTED', now(), now())"
            ), {"id": goal_id})
        else:
            connection.execute(text(
                "INSERT INTO goal_checkpoints (owner_id, goal_id, amount_cents, "
                "created_at, updated_at) VALUES ('postgres-money-test', :id, "
                "100, now(), now())"
            ), {"id": goal_id})

    refused = _alembic(
        postgres_url, "downgrade", "0018_goal_core", succeeds=False,
    )
    assert "Cannot downgrade Goal Composition" in refused.stderr
    with pg_engine.connect() as connection:
        assert connection.scalar(text(
            "SELECT version_num FROM alembic_version"
        )) == "0024_restore_publish_keys"
        assert table in inspect(pg_engine).get_table_names()
        assert connection.scalar(text(f"SELECT COUNT(*) FROM {table}")) == 1


def test_postgres_parent_delete_restricts_child_rows_even_outside_api(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "head")
    goal = _goal(pg_client)
    response = pg_client.post(
        f"/serenity-api/goals/{goal['id']}/checkpoints",
        json={"amount": "1.00"},
    )
    assert response.status_code == 201, response.text
    with pytest.raises(IntegrityError):
        with pg_engine.begin() as connection:
            connection.execute(
                text("DELETE FROM goals WHERE id = :id"),
                {"id": goal["id"]},
            )
    assert pg_client.get(f"/serenity-api/goals/{goal['id']}").status_code == 200