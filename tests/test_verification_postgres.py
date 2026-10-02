"""Owner evidence on disposable PostgreSQL: permissions and unchanged guards."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.system_health import system_health
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401
from tests.test_verification import PATH, payload


@pytest.fixture(autouse=True)
def isolated(postgres_url, pg_engine):
    assert "/isolated-money-pg" in postgres_url
    with pg_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))
    _alembic(postgres_url, "upgrade", "head")


def test_pg_save_replace_delete_preserves_balance(pg_client):
    debt = pg_client.post("/serenity-api/debts", json={
        "name": "Synthetic", "balance": "123.00",
    })
    assert debt.status_code == 201, debt.text
    report = pg_client.get(PATH)
    assert report.status_code == 200, report.text
    t = report.json()["targets"][0]
    url = f'{PATH}/{t["kind"]}/{t["target_id"]}'
    first = pg_client.put(url, json=payload(t))
    assert first.status_code == 200, first.text
    assert first.json()["recorded_at"].endswith("+00:00")
    assert pg_client.get(PATH).json()["targets"][0]["status"] == "VERIFIED"
    replaced = pg_client.put(url, json={**payload(t), "evidence": "New synthetic evidence"})
    assert replaced.json()["id"] == first.json()["id"]
    assert pg_client.get("/serenity-api/debts").json()[0]["balance"] == "123.00"
    assert pg_client.delete(f'{PATH}/{first.json()["id"]}').status_code == 204


def test_pg_existing_write_guard_not_bypassed(pg_client, pg_engine):
    from migrations.publish_key_references import REFERENCES
    pg_client.post("/serenity-api/debts", json={"name": "Synthetic", "balance": "1.00"})
    t = pg_client.get(PATH).json()["targets"][0]
    table, constraint, *_ = REFERENCES[0]
    with pg_engine.begin() as connection:
        connection.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{constraint}"'))
    response = pg_client.put(f'{PATH}/{t["kind"]}/{t["target_id"]}', json=payload(t))
    assert response.status_code == 503
    assert pg_client.get(PATH).json()["targets"][0]["status"] == "UNKNOWN"


def test_pg_optional_evidence_permission_not_runtime_state(pg_engine):
    with pg_engine.begin() as connection:
        connection.execute(text("CREATE ROLE verification_reader NOLOGIN"))
        connection.execute(text("GRANT USAGE ON SCHEMA public TO verification_reader"))
        connection.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO verification_reader"))
        connection.execute(text("REVOKE SELECT ON manual_verifications FROM verification_reader"))
    with Session(pg_engine) as db:
        db.execute(text("SET LOCAL ROLE verification_reader"))
        assert system_health(db, application_version="synthetic")["state"] == "NORMAL"