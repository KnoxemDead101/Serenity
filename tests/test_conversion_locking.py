"""Synthetic cross-session tests for the shared financial write lock."""

import threading
import uuid

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from services.financial_write_lock import lock_owner_financial_writes
from test_money_postgres import pg_engine, postgres_url  # noqa: F401


def _assert_same_owner_writers_serialize(engine, owner_id):
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    first_acquired = threading.Event()
    release_first = threading.Event()
    second_acquired = threading.Event()
    errors = []

    def first_writer():
        try:
            with sessions.begin() as db:
                lock_owner_financial_writes(db, owner_id)
                first_acquired.set()
                if not release_first.wait(5):
                    raise AssertionError("Timed out waiting to release the first writer")
        except BaseException as exc:  # propagate failures from worker threads
            errors.append(exc)

    def second_writer():
        try:
            with sessions.begin() as db:
                if not first_acquired.wait(5):
                    raise AssertionError("The first writer did not acquire its lock")
                lock_owner_financial_writes(db, owner_id)
                second_acquired.set()
        except BaseException as exc:
            errors.append(exc)

    first = threading.Thread(target=first_writer)
    second = threading.Thread(target=second_writer)
    first.start()
    second.start()
    try:
        assert first_acquired.wait(5)
        assert not second_acquired.wait(0.2)
    finally:
        release_first.set()
        first.join(5)
        second.join(5)

    assert not first.is_alive() and not second.is_alive()
    assert not errors
    assert second_acquired.is_set()


def test_sqlite_owner_financial_writes_serialize_on_synthetic_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'financial-lock-test.db'}")
    try:
        _assert_same_owner_writers_serialize(engine, "synthetic-owner")
    finally:
        engine.dispose()


def test_postgresql_owner_financial_writes_serialize_on_synthetic_database(
    postgres_url, pg_engine,
):
    # Do not fall back to DATABASE_URL: this test must never run against the
    # application's configured database unless an isolated test URL is given.
    # Only the fixture-created private cluster supplies that isolated URL.
    assert postgres_url.startswith("postgresql://moneytest@/postgres?host=/tmp/")
    assert "/isolated-money-pg" in postgres_url and "/socket" in postgres_url
    _assert_same_owner_writers_serialize(pg_engine, f"synthetic-{uuid.uuid4()}")