"""Real runtime safety states on a disposable PostgreSQL server only."""

import pytest
from sqlalchemy import text
from sqlalchemy.orm import Session

from services.system_health import system_health
from services.data_health import data_health
from test_money_postgres import _alembic, pg_client, pg_engine, postgres_url  # noqa: F401


@pytest.fixture(autouse=True)
def isolated_schema(postgres_url, pg_engine):
    assert postgres_url.startswith("postgresql://moneytest@/postgres?host=/tmp/")
    assert "/isolated-money-pg" in postgres_url
    with pg_engine.begin() as connection:
        connection.execute(text("DROP SCHEMA public CASCADE"))
        connection.execute(text("CREATE SCHEMA public"))


def test_pg_staging_without_work_schema_is_unavailable_and_restoration_is_normal(postgres_url, pg_client):
    _alembic(postgres_url, "upgrade", "0022_publish_key_stage")
    staged = pg_client.get("/serenity-api/system/health").json()
    # A historical staging schema lacks the newly required work domain. The
    # model-driven console must not label missing application tables readable.
    assert staged["state"] == "UNAVAILABLE"
    assert staged["checks"][1]["status"] == "UNAVAILABLE"
    assert not staged["writes_enabled"]
    assert staged["migration"]["status"] == "UNVERIFIED"
    # Health is read-only evidence; the real write guard still blocks mutation.
    assert pg_client.post("/serenity-api/portfolios", json={"name": "Blocked"}).status_code == 503
    _alembic(postgres_url, "upgrade", "head")
    restored = pg_client.get("/serenity-api/system/health").json()
    assert restored["state"] == "NORMAL"
    assert restored["migration"]["status"] == "CURRENT"
    assert pg_client.post("/serenity-api/portfolios", json={"name": "Synthetic"}).status_code == 201


def test_pg_readable_current_schema_with_missing_financial_guard_is_read_only(
    postgres_url, pg_engine, pg_client,
):
    from migrations.publish_key_references import REFERENCES

    _alembic(postgres_url, "upgrade", "head")
    table, constraint, *_ = REFERENCES[0]
    # Only this disposable cluster is altered, to isolate write-guard health
    # from the separate missing-domain schema observation above.
    with pg_engine.begin() as connection:
        connection.execute(text(f'ALTER TABLE "{table}" DROP CONSTRAINT "{constraint}"'))
    report = pg_client.get("/serenity-api/system/health").json()
    assert report["state"] == "READ_ONLY"
    assert report["checks"][1]["status"] == "AVAILABLE"
    assert not report["writes_enabled"]
    assert report["migration"]["status"] == "CURRENT"
    assert pg_client.post("/serenity-api/portfolios", json={"name": "Blocked"}).status_code == 503


@pytest.mark.parametrize("damage", ["table", "column", "permission"])
def test_pg_missing_or_hidden_schema_is_unavailable(postgres_url, pg_engine, damage):
    _alembic(postgres_url, "upgrade", "head")
    with Session(pg_engine) as db:
        if damage == "table":
            db.execute(text("DROP TABLE goals CASCADE"))
        elif damage == "column":
            db.execute(text("ALTER TABLE goals RENAME COLUMN name TO hidden_name"))
        else:
            db.execute(text("CREATE ROLE health_reader NOLOGIN"))
            db.execute(text("GRANT USAGE ON SCHEMA public TO health_reader"))
            db.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO health_reader"))
            db.execute(text("REVOKE SELECT ON goals FROM health_reader"))
            db.execute(text("SET LOCAL ROLE health_reader"))
        data = system_health(db, application_version="test")
        assert data["state"] == "UNAVAILABLE"
        assert data["checks"][0]["status"] == "AVAILABLE"
        assert not data["writes_enabled"]
        assert "Unknown does not mean empty" in data["message"]
        db.rollback()


def test_managed_schema_without_version_tracking_is_not_missing_data(
    postgres_url, pg_engine, pg_client,
):
    _alembic(postgres_url, "upgrade", "head")
    with pg_engine.begin() as connection:
        connection.execute(text("DROP TABLE alembic_version"))
    data = pg_client.get("/serenity-api/system/health").json()
    assert data["state"] == "NORMAL"
    assert data["migration"]["status"] == "UNVERIFIED"
    assert data["migration"]["observed_revision"] is None


def test_data_read_failure_savepoint_keeps_other_domains_readable(postgres_url, pg_engine):
    _alembic(postgres_url, "upgrade", "head")
    with Session(pg_engine) as db:
        db.execute(text("CREATE ROLE data_health_reader NOLOGIN"))
        db.execute(text("GRANT USAGE ON SCHEMA public TO data_health_reader"))
        db.execute(text("GRANT SELECT ON ALL TABLES IN SCHEMA public TO data_health_reader"))
        db.execute(text("REVOKE SELECT ON debts FROM data_health_reader"))
        db.execute(text("SET LOCAL ROLE data_health_reader"))
        report = data_health(db, "test-owner")
        readings = {r["key"]: r for r in report["readings"]}
        assert readings["debts"]["status"] == "UNAVAILABLE"
        assert readings["debts"]["record_count"] is None
        assert readings["investments"]["status"] == "MISSING"
        assert readings["income"]["status"] == "MISSING"
        assert db.scalar(text("SELECT 1")) == 1
        db.rollback()