"""Tests that financial pages, APIs, and downloads require a Serenity session."""

from auth import AUTH_COOKIE, issue_session


def test_unauthorized_visitors_cannot_reach_financial_pages(client):
    client.app.state.auth_bypass = False
    try:
        for path in ("/", "/accounts", "/finances", "/setup"):
            response = client.get(path, follow_redirects=False)
            assert response.status_code == 307
            assert response.headers["location"].startswith("/sign-in")
    finally:
        client.app.state.auth_bypass = True


def test_unauthorized_visitors_cannot_reach_financial_apis_or_downloads(client):
    client.app.state.auth_bypass = False
    try:
        for path in (
            "/serenity-api/accounts",
            "/serenity-api/dashboard/summary",
            "/serenity-api/export",
            "/serenity-api/export/transactions.csv",
        ):
            assert client.get(path).status_code == 401
    finally:
        client.app.state.auth_bypass = True


def test_signed_session_can_reach_financial_data(client):
    client.app.state.auth_bypass = False
    client.cookies.set(AUTH_COOKIE, issue_session("invited-user"))
    try:
        assert client.get("/").status_code == 200
        assert client.get("/serenity-api/accounts").status_code == 200
        assert client.get("/serenity-api/export").status_code == 200
    finally:
        client.app.state.auth_bypass = True