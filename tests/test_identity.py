"""Real auth ownership tests use an isolated DB and fake Clerk session IDs."""

import pytest
from sqlalchemy import func, select

from auth import AUTH_COOKIE, issue_session
from conftest import TEST_CLERK_ISSUER, sign_in_as
from models.account import Account
from models.identity import AuthIdentity, SerenityUser, Workspace
from services import identity_service

ACCOUNT = {
    "name": "Checking", "account_type": "Checking",
    "classification": "Personal", "opening_balance": "10.00",
}


def count(db, model):
    return db.scalar(select(func.count()).select_from(model))


def test_verified_identity_owns_workspace_not_external_id(real_auth_client, db):
    sign_in_as(real_auth_client, "clerk-user-a")
    created = real_auth_client.post("/serenity-api/accounts", json=ACCOUNT)
    assert created.status_code == 201
    workspace = db.scalars(select(Workspace)).one()
    assert db.get(Account, created.json()["id"]).owner_id == workspace.id
    assert workspace.id != "clerk-user-a"
    assert (count(db, SerenityUser), count(db, AuthIdentity)) == (1, 1)
    assert real_auth_client.get("/serenity-api/auth/me").json() == {
        "user_id": "clerk-user-a", "workspace_id": workspace.id,
    }
    assert real_auth_client.get("/serenity-api/accounts").status_code == 200
    assert count(db, Workspace) == 1


def test_two_subjects_isolated_including_exports(real_auth_client, db):
    sign_in_as(real_auth_client, "clerk-user-a")
    account_id = real_auth_client.post("/serenity-api/accounts", json=ACCOUNT).json()["id"]
    sign_in_as(real_auth_client, "clerk-user-b")
    assert real_auth_client.get("/serenity-api/accounts").json() == []
    assert real_auth_client.get(f"/serenity-api/accounts/{account_id}").status_code == 404
    assert count(db, Workspace) == 2


def test_same_subject_different_issuers_distinct(db):
    first = identity_service.workspace_for_identity(
        db, provider="clerk", issuer=TEST_CLERK_ISSUER, subject="same")
    second = identity_service.workspace_for_identity(
        db, provider="clerk", issuer="https://other.example.test", subject="same")
    assert first != second


def test_deactivation_applies_each_request_export_page_and_exchange(real_auth_client, db, monkeypatch):
    sign_in_as(real_auth_client, "clerk-user-a")
    assert real_auth_client.post("/serenity-api/accounts", json=ACCOUNT).status_code == 201
    user_id = db.scalars(select(SerenityUser.id)).one()
    identity_service.set_user_active(db, user_id, False)
    for method, path in (
        ("get", "/serenity-api/accounts"), ("get", "/serenity-api/export"),
        ("get", "/serenity-api/auth/me"), ("get", "/accounts"),
        ("post", "/serenity-api/accounts"),
    ):
        result = getattr(real_auth_client, method)(path, follow_redirects=False)
        assert result.status_code == 403
        assert result.headers["x-serenity-account-status"] == "inactive"
    assert count(db, Account) == 1
    # An authenticated token exchange must not issue another cookie.
    monkeypatch.setattr("main.verify_clerk_token", lambda token: ("clerk-user-a", "fixture-clerk-user-a"))
    exchanged = real_auth_client.post("/serenity-api/auth/session", headers={"Authorization": "Bearer synthetic"})
    assert exchanged.status_code == 403
    assert exchanged.headers["x-serenity-account-status"] == "inactive"
    assert "set-cookie" not in exchanged.headers


def test_missing_config_for_signed_cookie_and_exchange_is_503(real_auth_client, monkeypatch, db):
    sign_in_as(real_auth_client, "clerk-user-a")
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY")
    for path in ("/serenity-api/accounts", "/serenity-api/auth/me", "/accounts"):
        result = real_auth_client.get(path, follow_redirects=False)
        assert result.status_code == 503
    exchange = real_auth_client.post("/serenity-api/auth/session",
                                     headers={"Authorization": "Bearer broken"})
    assert exchange.status_code == 503
    assert "set-cookie" not in exchange.headers
    assert count(db, Workspace) == 0


def test_last_sign_in_only_on_exchange(db):
    identity_service.workspace_for_identity(
        db, provider="clerk", issuer=TEST_CLERK_ISSUER, subject="quiet")
    identity_service.workspace_for_identity(
        db, provider="clerk", issuer=TEST_CLERK_ISSUER, subject="signed-in",
        record_sign_in=True)
    stamps = dict(db.execute(select(AuthIdentity.subject, AuthIdentity.last_sign_in_at)).all())
    assert stamps["quiet"] is None
    assert stamps["signed-in"] is not None