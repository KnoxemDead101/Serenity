"""Tests that financial pages, APIs, and downloads require a live Clerk session."""

import time

import auth
from auth import AUTH_COOKIE, issue_session


def test_unauthorized_visitors_cannot_reach_financial_pages(real_auth_client):
    for path in ("/", "/accounts", "/finances", "/income", "/setup"):
        response = real_auth_client.get(path, follow_redirects=False)
        assert response.status_code == 307
        assert response.headers["location"].startswith("/sign-in")


def test_unauthorized_visitors_cannot_reach_financial_apis_or_downloads(real_auth_client):
    for path in (
        "/serenity-api/accounts",
        "/serenity-api/dashboard/summary",
        "/serenity-api/export",
        "/serenity-api/export/transactions.csv",
        "/serenity-api/income-profiles",
    ):
        assert real_auth_client.get(path).status_code == 401


def test_signed_session_can_reach_financial_data(real_auth_client):
    real_auth_client.cookies.set(AUTH_COOKIE, issue_session("invited-user", "fixture-invited-user"))
    assert real_auth_client.get("/").status_code == 200
    assert real_auth_client.get("/serenity-api/accounts").status_code == 200
    assert real_auth_client.get("/serenity-api/export").status_code == 200
    assert real_auth_client.get("/serenity-api/income-profiles").status_code == 200


def test_signed_out_visitors_cannot_write(real_auth_client):
    response = real_auth_client.post("/serenity-api/accounts", json={
        "name": "No owner", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "0",
    })
    assert response.status_code == 401


def test_tampered_and_expired_cookies_are_rejected(real_auth_client, monkeypatch):
    import auth

    real_auth_client.cookies.set(AUTH_COOKIE, "not-a-valid-session")
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    real_auth_client.cookies.set(AUTH_COOKIE, issue_session("expired-user", "fixture-expired-user"))
    monkeypatch.setattr(auth.time, "time", lambda: 4_000_000_000)
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401


def test_sign_out_clears_cookie(real_auth_client):
    real_auth_client.cookies.set(AUTH_COOKIE, issue_session("signed-in-user", "fixture-signed-in-user"))
    response = real_auth_client.delete("/serenity-api/auth/session")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False}
    assert "max-age=0" in response.headers["set-cookie"].lower()
    real_auth_client.cookies.clear()
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401


def test_page_redirect_preserves_requested_query(real_auth_client):
    response = real_auth_client.get(
        "/accounts?filter=checking", follow_redirects=False
    )
    assert response.status_code == 307
    assert response.headers["location"].endswith(
        "/sign-in?next=/accounts?filter=checking"
    )


def test_legacy_cookie_requires_new_clerk_sign_in(real_auth_client, monkeypatch):
    # Old cookies did not bind to any Clerk session: even a valid signature
    # cannot justify access after revocation.
    monkeypatch.setattr(auth, "_live_clerk_session", lambda *args: 1 / 0)
    real_auth_client.cookies.set(AUTH_COOKIE, auth._encode({
        "user_id": "invited-user", "expires_at": int(time.time()) + 3600,
    }))
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    assert real_auth_client.get("/", follow_redirects=False).status_code == 307


def test_bad_session_identifier_in_signed_cookie_is_rejected(real_auth_client, monkeypatch):
    monkeypatch.setattr(auth, "_live_clerk_session", lambda *args: 1 / 0)
    real_auth_client.cookies.set(AUTH_COOKIE, auth._encode({
        "user_id": "invited-user", "clerk_session_id": "../another-session",
        "expires_at": int(time.time()) + 3600,
    }))
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401


def test_revoked_fixture_cookie_denies_api_writes_and_pages(real_auth_client, monkeypatch):
    real_auth_client.cookies.set(
        AUTH_COOKIE, issue_session("invited-user", "fixture-invited-user")
    )
    assert real_auth_client.get("/serenity-api/accounts").status_code == 200
    monkeypatch.setattr(auth, "_live_clerk_session", lambda *args: False)
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    assert real_auth_client.post("/serenity-api/accounts", json={
        "name": "Denied", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "0",
    }).status_code == 401
    assert real_auth_client.get("/serenity-api/export").status_code == 401
    assert real_auth_client.get("/accounts", follow_redirects=False).status_code == 307