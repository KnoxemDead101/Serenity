"""
Shared test setup (pytest loads this file automatically).

Every test gets a brand-new, EMPTY database that lives only in memory.
That means:
- tests never touch your real serenity.db file,
- tests can't affect each other,
- they run fast.
"""

import os
from urllib.parse import urlsplit

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
import models.income_profile  # noqa: F401
import models.transaction  # noqa: F401
import models.transaction_correction  # noqa: F401
import auth
from auth import AUTH_COOKIE, issue_session, require_page_session, require_session
from main import app
from storage.database import Base, get_db

TEST_OWNER_ID = "test-owner"


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
def client(db, monkeypatch):
    """
    A fake browser that calls the API without starting a real server.
    Requests are signed in as the explicit test owner.
    """
    app.dependency_overrides[get_db] = lambda: db
    app.dependency_overrides[require_session] = lambda: TEST_OWNER_ID
    app.dependency_overrides[require_page_session] = lambda: TEST_OWNER_ID
    live_lookup = auth._live_clerk_session

    def fixture_lookup(session_id, user_id):
        # Only locally signed, explicitly prefixed test fixture cookies use
        # this synthetic session; genuine RSA handoff tests use HTTP mocks.
        if session_id.startswith("fixture-"):
            return session_id == f"fixture-{user_id}"
        return live_lookup(session_id, user_id)

    monkeypatch.setattr(auth, "_live_clerk_session", fixture_lookup)
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def real_auth_client(client):
    """Client with real cookie authentication instead of test overrides."""
    app.dependency_overrides.pop(require_session, None)
    app.dependency_overrides.pop(require_page_session, None)
    client.cookies.clear()
    yield client


def sign_in_as(client, user_id: str) -> None:
    client.cookies.set(AUTH_COOKIE, issue_session(user_id, f"fixture-{user_id}"))


def _browser_unavailable(reason: str) -> None:
    if os.getenv("SERENITY_REQUIRE_BROWSER") == "1":
        pytest.fail(reason)
    pytest.skip(reason)


@pytest.fixture
def page(client):
    """Headless Chromium page served by the in-memory FastAPI test app."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        _browser_unavailable("Playwright is not installed")
    import shutil

    executable = next(
        (shutil.which(name) for name in ("chromium", "chromium-browser", "google-chrome")
         if shutil.which(name)),
        None,
    )
    if executable is None:
        _browser_unavailable("Chromium is not installed")
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=executable, headless=True, args=["--no-sandbox"]
        )
        page = browser.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))

        def dispatch(route):
            request = route.request
            parts = urlsplit(request.url)
            path = parts.path + (f"?{parts.query}" if parts.query else "")
            response = client.request(
                request.method,
                path,
                content=request.post_data_buffer,
                headers={"content-type": request.headers.get("content-type", "")},
            )
            route.fulfill(
                status=response.status_code,
                body=response.content,
                headers={"content-type": response.headers.get("content-type", "text/plain")},
            )

        page.route("**/*", dispatch)
        try:
            yield page
            assert errors == [], f"Uncaught browser errors: {errors}"
        finally:
            browser.close()
