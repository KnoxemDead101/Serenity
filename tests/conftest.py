"""
Shared test setup (pytest loads this file automatically).

Every test gets a brand-new, EMPTY database that lives only in memory.
That means:
- tests never touch your real serenity.db file,
- tests can't affect each other,
- they run fast.
"""

import os

if os.getenv("DATABASE_URL", "").startswith("postgresql"):
    os.environ["DATABASE_URL"] = "sqlite://"
os.environ.setdefault("SESSION_SECRET", "test-session-secret")

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import models.account  # noqa: F401  (registers the accounts table)
import models.bill  # noqa: F401
import models.business  # noqa: F401
import models.debt  # noqa: F401
import models.dependent  # noqa: F401
import models.investment  # noqa: F401
import models.transaction  # noqa: F401
import models.transaction_correction  # noqa: F401
from main import app
from storage.database import Base, get_db

app.state.auth_bypass = True


@pytest.fixture
def db():
    """A database session connected to a fresh in-memory SQLite database."""
    engine = create_engine(
        "sqlite://",  # no file name = in memory
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,  # every connection shares the same memory DB
    )
    Base.metadata.create_all(bind=engine)
    TestingSession = sessionmaker(bind=engine, autoflush=False)
    session = TestingSession()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()


@pytest.fixture
def client(db):
    """
    A fake browser that calls the API without starting a real server.

    `dependency_overrides` swaps the real get_db for one that returns
    the in-memory test session.
    """
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()
