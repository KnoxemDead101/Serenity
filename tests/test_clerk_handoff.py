"""Exercise real RSA verification with local keys and mocked HTTP only."""

import base64
import io
import json
import time
import urllib.error
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

import auth

ISSUER = "https://clerk.example.test"
ORIGIN = "https://serenity.example.test"


@pytest.fixture
def clerk(monkeypatch):
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(private.public_key()))
    jwk.update(kid="trusted", use="sig", alg="RS256")
    monkeypatch.setenv("CLERK_SECRET_KEY", "unit-test-only")
    monkeypatch.setenv("CLERK_PUBLISHABLE_KEY", "pk_test_" + base64.b64encode(
        b"clerk.example.test$").decode())
    monkeypatch.setenv("SERENITY_AUTHORIZED_PARTIES", ORIGIN)
    monkeypatch.delenv("SERENITY_DEV", raising=False)
    auth._jwks_client.cache_clear()
    state = {"session": {"status": "active", "user_id": "user-test"}, "calls": []}

    def lookup(request, timeout, **kwargs):
        assert request.get_header("User-agent") == "Serenity/1.0"
        assert request.get_header("Accept") == "application/json"
        assert timeout == 8
        state["calls"].append(request.full_url)
        if request.full_url == ISSUER + "/.well-known/jwks.json":
            return io.BytesIO(json.dumps({"keys": [jwk]}).encode())
        assert request.full_url in (
            "https://api.clerk.com/v1/sessions/session-test",
            "https://api.clerk.com/v1/sessions/session-other",
        )
        if state.get("blocked"):
            raise urllib.error.HTTPError(request.full_url, 403, "Forbidden", {}, None)
        if state.get("offline"):
            raise urllib.error.URLError("offline")
        session = (
            state["session"] if request.full_url.endswith("/session-test")
            else state.get("other_session", {"status": "revoked", "user_id": "user-test"})
        )
        return io.BytesIO(json.dumps(session).encode())

    monkeypatch.setattr(auth.urllib.request, "urlopen", lookup)
    monkeypatch.setattr(auth.urllib.request, "build_opener",
                        lambda *args: SimpleNamespace(open=lookup))

    def token(updates=None, omit=(), key=None, algorithm="RS256", kid="trusted"):
        now = int(time.time())
        claims = dict(iss=ISSUER, sid="session-test", sub="user-test",
                      exp=now + 60, nbf=now - 1, iat=now - 1, azp=ORIGIN)
        claims.update(updates or {})
        for field in omit:
            claims.pop(field)
        return jwt.encode(claims, key or private, algorithm=algorithm,
                          headers={"kid": kid})

    state["token"] = token
    yield state
    auth._jwks_client.cache_clear()


def exchange(client, token, **headers):
    return client.post("/serenity-api/auth/session",
                       headers={"Authorization": f"Bearer {token}", **headers})


def test_session_lookup_uses_application_headers(real_auth_client, clerk):
    response = exchange(real_auth_client, clerk["token"]())
    assert response.status_code == 200
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    assert auth._decode(response.cookies[auth.AUTH_COOKIE])["user_id"] == "user-test"
    assert auth._decode(response.cookies[auth.AUTH_COOKIE])["clerk_session_id"] == "session-test"


@pytest.mark.parametrize("updates,omit", [
    ({"iss": "https://attacker.example"}, ()),
    ({"exp": 1}, ()),
    ({"nbf": 4_000_000_000}, ()),
    ({"iat": 4_000_000_000}, ()),
    ({"exp": "4000000000"}, ()),
    ({"sub": ""}, ()),
    ({"sid": "../sessions/other"}, ()),
    ({"sid": []}, ()),
    ({"azp": "https://attacker.example"}, ()),
    ({"azp": None}, ()),
    *[({}, (field,)) for field in ("exp", "nbf", "iat", "iss", "sub", "sid", "azp")],
])
def test_invalid_claims_cannot_mint_cookie(real_auth_client, clerk, updates, omit):
    response = exchange(real_auth_client, clerk["token"](updates, omit),
                        Origin="https://attacker.example")
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert all(url.startswith(ISSUER) for url in clerk["calls"])


def test_forged_signature_cannot_mint_cookie(real_auth_client, clerk):
    attacker = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    response = exchange(real_auth_client, clerk["token"](key=attacker))
    assert response.status_code == 401
    assert "set-cookie" not in response.headers
    assert clerk["calls"] == [ISSUER + "/.well-known/jwks.json"]


@pytest.mark.parametrize("token", ["garbage", "a.b.c", "", "e30.e30."])
def test_malformed_tokens_fail_closed(real_auth_client, clerk, token):
    response = exchange(real_auth_client, token)
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_wrong_algorithm_and_unknown_key_fail_closed(real_auth_client, clerk):
    for token in (
        clerk["token"](key="attacker-key-" * 4, algorithm="HS256"),
        clerk["token"](kid="unknown"),
    ):
        response = exchange(real_auth_client, token)
        assert response.status_code == 401
        assert "set-cookie" not in response.headers


def test_blocked_backend_fails_closed_without_logging_tokens(clerk, caplog):
    clerk["blocked"] = True
    bearer = clerk["token"]()
    assert auth.verify_clerk_token(bearer) is None
    assert "HTTP 403" in caplog.text
    assert bearer not in caplog.text
    assert "unit-test-only" not in caplog.text


@pytest.mark.parametrize("session", [
    {"status": "revoked", "user_id": "user-test"},
    {"status": "active", "user_id": "someone-else"},
    [],
])
def test_inactive_or_mismatched_session_is_rejected(clerk, session):
    clerk["session"] = session
    assert auth.verify_clerk_token(clerk["token"]()) is None


def test_missing_trust_configuration_fails_closed(clerk, monkeypatch):
    monkeypatch.delenv("SERENITY_AUTHORIZED_PARTIES")
    assert auth.verify_clerk_token(clerk["token"]()) is None
    monkeypatch.delenv("CLERK_PUBLISHABLE_KEY")
    assert auth.verify_clerk_token(clerk["token"]()) is None


@pytest.mark.parametrize("body", [b"not json", b"[]", b'{"keys": []}'])
def test_bad_jwks_cannot_mint_cookie(real_auth_client, clerk, monkeypatch, body):
    monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *args:
                        SimpleNamespace(open=lambda *args, **kwargs: io.BytesIO(body)))
    response = exchange(real_auth_client, clerk["token"]())
    assert response.status_code == 401
    assert "set-cookie" not in response.headers


def test_unavailable_jwks_fails_closed(real_auth_client, clerk, monkeypatch):
    def unavailable(*args, **kwargs):
        raise urllib.error.URLError("offline")
    monkeypatch.setattr(auth.urllib.request, "build_opener", lambda *args:
                        SimpleNamespace(open=unavailable))
    assert exchange(real_auth_client, clerk["token"]()).status_code == 401


def test_verified_users_have_isolated_accounts(real_auth_client, clerk):
    real_auth_client.base_url = "https://testserver"
    assert exchange(real_auth_client, clerk["token"]()).status_code == 200
    created = real_auth_client.post("/serenity-api/accounts", json={
        "name": "Private", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "0",
    })
    assert created.status_code == 201
    account_id = created.json()["id"]
    clerk["session"]["user_id"] = "other-user"
    assert exchange(real_auth_client, clerk["token"]({"sub": "other-user"})).status_code == 200
    assert real_auth_client.get(f"/serenity-api/accounts/{account_id}").status_code == 404
    assert real_auth_client.get("/serenity-api/accounts").json() == []


def test_revocation_after_verified_handoff_denies_all_financial_routes(real_auth_client, clerk):
    real_auth_client.base_url = "https://testserver"
    assert exchange(real_auth_client, clerk["token"]()).status_code == 200
    assert real_auth_client.get("/serenity-api/accounts").status_code == 200
    clerk["session"]["status"] = "revoked"
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    assert real_auth_client.post("/serenity-api/accounts", json={
        "name": "Denied", "account_type": "Checking",
        "classification": "Personal", "opening_balance": "0",
    }).status_code == 401
    assert real_auth_client.get("/serenity-api/export/transactions.csv").status_code == 401
    response = real_auth_client.get("/accounts", follow_redirects=False)
    assert response.status_code == 307
    assert response.headers["location"].startswith("/sign-in")


def test_clerk_outage_and_owner_mismatch_fail_closed_after_handoff(real_auth_client, clerk):
    real_auth_client.base_url = "https://testserver"
    assert exchange(real_auth_client, clerk["token"]()).status_code == 200
    clerk["session"]["user_id"] = "other-user"
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    clerk["session"]["user_id"] = "user-test"
    clerk["blocked"] = True
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    clerk["blocked"] = False
    clerk["offline"] = True
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    clerk["offline"] = False
    assert real_auth_client.get("/serenity-api/accounts").status_code == 200


def test_second_session_same_owner_does_not_rescue_revoked_cookie(real_auth_client, clerk):
    real_auth_client.base_url = "https://testserver"
    assert exchange(real_auth_client, clerk["token"]()).status_code == 200
    original_cookie = real_auth_client.cookies[auth.AUTH_COOKIE]
    clerk["other_session"] = {"status": "active", "user_id": "user-test"}
    assert exchange(real_auth_client, clerk["token"]({"sid": "session-other"})).status_code == 200
    other_cookie = real_auth_client.cookies[auth.AUTH_COOKIE]
    clerk["session"]["status"] = "revoked"
    real_auth_client.cookies.set(auth.AUTH_COOKIE, original_cookie)
    assert real_auth_client.get("/serenity-api/accounts").status_code == 401
    real_auth_client.cookies.set(auth.AUTH_COOKIE, other_cookie)
    assert real_auth_client.get("/serenity-api/accounts").status_code == 200


def test_duplicate_auth_checks_share_one_request_lookup(real_auth_client, clerk):
    real_auth_client.base_url = "https://testserver"
    assert exchange(real_auth_client, clerk["token"]()).status_code == 200
    clerk["calls"].clear()
    assert real_auth_client.get("/serenity-api/auth/me").status_code == 200
    assert clerk["calls"] == ["https://api.clerk.com/v1/sessions/session-test"]
    assert real_auth_client.get("/serenity-api/auth/me").status_code == 200
    assert len(clerk["calls"]) == 2