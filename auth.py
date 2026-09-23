"""Authentication helpers for the Serenity web application.

Clerk handles sign-in and invitation management.  Serenity exchanges a
verified Clerk session token for a short-lived, signed HTTP-only cookie so
that Python page and API routes can enforce authentication server-side.
"""

import base64
import hashlib
import hmac
import json
import os
import time
import urllib.error
import urllib.request
from typing import Any

from fastapi import HTTPException, Request, status

AUTH_COOKIE = "serenity_session"
SESSION_TTL_SECONDS = 60 * 60 * 12


def _auth_bypass_enabled() -> bool:
    """Allow the existing isolated test suite to exercise business routes."""
    return bool(getattr(request_app_state(), "auth_bypass", False))


def request_app_state():
    """Return the app state set by the test harness, when present."""
    from main import app

    return app.state


def _secret() -> bytes:
    secret = os.getenv("SESSION_SECRET")
    if not secret:
        raise RuntimeError("SESSION_SECRET must be configured")
    return secret.encode("utf-8")


def _encode(value: dict[str, Any]) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps(value, separators=(",", ":")).encode("utf-8")
    ).rstrip(b"=").decode("ascii")
    signature = hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest()
    encoded_signature = base64.urlsafe_b64encode(signature).rstrip(b"=").decode("ascii")
    return f"{payload}.{encoded_signature}"


def _decode(value: str) -> dict[str, Any] | None:
    try:
        payload, signature = value.split(".", 1)
        expected = hmac.new(_secret(), payload.encode("ascii"), hashlib.sha256).digest()
        supplied = base64.urlsafe_b64decode(signature + "=" * (-len(signature) % 4))
        if not hmac.compare_digest(expected, supplied):
            return None
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        session = json.loads(decoded)
        if not isinstance(session, dict) or session.get("expires_at", 0) < time.time():
            return None
        if not session.get("user_id"):
            return None
        return session
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def issue_session(user_id: str) -> str:
    return _encode(
        {
            "user_id": user_id,
            "expires_at": int(time.time()) + SESSION_TTL_SECONDS,
        }
    )


def current_user(request: Request) -> str | None:
    """Return the authenticated Clerk user id from Serenity's signed cookie."""
    if _auth_bypass_enabled():
        return "test-user"
    cookie = request.cookies.get(AUTH_COOKIE)
    if not cookie:
        return None
    session = _decode(cookie)
    return str(session["user_id"]) if session else None


def require_session(request: Request) -> str:
    user_id = current_user(request)
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
        )
    return user_id


def require_page_session(request: Request) -> str:
    user_id = current_user(request)
    if user_id is None:
        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": f"/sign-in?next={next_path}"},
            detail="Sign in required",
        )
    return user_id


def _jwt_payload(token: str) -> dict[str, Any] | None:
    """Read the signed token claims; Clerk performs the authoritative check."""
    try:
        parts = token.split(".")
        if len(parts) != 3:
            return None
        payload = base64.urlsafe_b64decode(parts[1] + "=" * (-len(parts[1]) % 4))
        claims = json.loads(payload)
        return claims if isinstance(claims, dict) else None
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def verify_clerk_token(token: str) -> str | None:
    """Verify a Clerk session through Clerk's Backend API and return user id."""
    claims = _jwt_payload(token)
    if not claims or not claims.get("sid") or not claims.get("sub"):
        return None
    if claims.get("exp", 0) < time.time():
        return None

    secret = os.getenv("CLERK_SECRET_KEY")
    if not secret:
        return None
    request = urllib.request.Request(
        f"https://api.clerk.com/v1/sessions/{claims['sid']}",
        headers={"Authorization": f"Bearer {secret}"},
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            session = json.loads(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError):
        return None

    if session.get("status") != "active" or session.get("user_id") != claims.get("sub"):
        return None
    return str(claims["sub"])


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None