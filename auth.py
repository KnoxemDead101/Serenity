"""Authentication helpers for the Serenity web application.

Clerk handles sign-in and invitation management. Serenity exchanges a
verified Clerk session token for a signed HTTP-only cookie bound to that
Clerk session. Protected requests recheck Clerk for revocation.
"""

import base64
import hashlib
import hmac
import json
import logging
import os
import re
import time
import urllib.error
import urllib.request
from urllib.parse import quote
from typing import Any
from functools import lru_cache

import jwt

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from services import identity_service
from storage.database import get_db

AUTH_COOKIE = "serenity_session"
SESSION_TTL_SECONDS = 60 * 60 * 12


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
        if not isinstance(session.get("user_id"), str) or not session["user_id"]:
            return None
        if not isinstance(session.get("clerk_session_id"), str) or not re.fullmatch(
            r"[A-Za-z0-9_-]+", session["clerk_session_id"]
        ):
            return None
        return session
    except (ValueError, TypeError, json.JSONDecodeError):
        return None


def issue_session(user_id: str, clerk_session_id: str) -> str:
    if not isinstance(clerk_session_id, str) or not re.fullmatch(
        r"[A-Za-z0-9_-]+", clerk_session_id
    ):
        raise ValueError("Valid Clerk session id required")
    return _encode(
        {
            "user_id": user_id,
            "clerk_session_id": clerk_session_id,
            "expires_at": int(time.time()) + SESSION_TTL_SECONDS,
        }
    )


class ClerkUnavailableError(Exception):
    """Authentication configuration or provider cannot currently be checked."""


def current_user(request: Request) -> str | None:
    """Return verified external subject, not a financial workspace id."""
    if hasattr(request.state, "serenity_current_user"):
        return request.state.serenity_current_user
    cookie = request.cookies.get(AUTH_COOKIE)
    if not cookie:
        return None
    session = _decode(cookie)
    user_id = (
        session["user_id"]
        if session and _live_clerk_session(session["clerk_session_id"], session["user_id"])
        else None
    )
    request.state.serenity_current_user = user_id
    return user_id


def configured_clerk_issuer() -> str:
    try:
        issuer = _clerk_issuer()
    except (ValueError, TypeError) as exc:
        raise ClerkUnavailableError("Sign-in is unavailable") from exc
    if not os.getenv("CLERK_SECRET_KEY"):
        raise ClerkUnavailableError("Sign-in is unavailable")
    return issuer


def _workspace_for_request(request: Request, db: Session, subject: str) -> str:
    if hasattr(request.state, "serenity_workspace_id"):
        return request.state.serenity_workspace_id
    try:
        workspace_id = identity_service.workspace_for_identity(
            db, provider=identity_service.CLERK_PROVIDER,
            issuer=configured_clerk_issuer(), subject=subject,
        )
    except identity_service.InactiveUserError as exc:
        raise HTTPException(
            status_code=403, detail="This Serenity account has been deactivated",
            headers={"X-Serenity-Account-Status": "inactive"},
        ) from exc
    except identity_service.IdentityError as exc:
        raise HTTPException(status_code=401, detail="Sign in required") from exc
    request.state.serenity_workspace_id = workspace_id
    return workspace_id


def _verified_subject(request: Request) -> str | None:
    if request.cookies.get(AUTH_COOKIE):
        # A signed cookie must not silently become an ordinary sign-in redirect
        # while Clerk is unavailable or server credentials are absent.
        configured_clerk_issuer()
    return current_user(request)


def require_session(request: Request, db: Session = Depends(get_db)) -> str:
    try:
        user_id = _verified_subject(request)
    except ClerkUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable") from exc
    if user_id is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Sign in required",
        )
    try:
        return _workspace_for_request(request, db, user_id)
    except ClerkUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable") from exc


def require_page_session(request: Request, db: Session = Depends(get_db)) -> str:
    try:
        user_id = _verified_subject(request)
    except ClerkUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable") from exc
    if user_id is None:
        next_path = request.url.path
        if request.url.query:
            next_path += f"?{request.url.query}"
        raise HTTPException(
            status_code=status.HTTP_307_TEMPORARY_REDIRECT,
            headers={"Location": f"/sign-in?next={quote(next_path, safe='/')}"},
            detail="Sign in required",
        )
    try:
        return _workspace_for_request(request, db, user_id)
    except ClerkUnavailableError as exc:
        raise HTTPException(status_code=503, detail="Sign-in is temporarily unavailable") from exc


def _clerk_issuer() -> str:
    """Derive trust from server configuration, never from incoming JWT claims."""
    key = os.getenv("CLERK_PUBLISHABLE_KEY", "")
    if not key.startswith(("pk_test_", "pk_live_")):
        raise ValueError("Missing Clerk configuration")
    encoded = key.split("_", 2)[2]
    host = base64.b64decode(encoded + "=" * (-len(encoded) % 4), validate=True).decode()
    if not host.endswith("$"):
        raise ValueError("Invalid Clerk configuration")
    host = host[:-1]
    if not re.fullmatch(r"[a-zA-Z0-9]+(?:[a-zA-Z0-9.-]*[a-zA-Z0-9])?", host):
        raise ValueError("Invalid Clerk host")
    return f"https://{host}"


@lru_cache(maxsize=4)
def _jwks_client(issuer: str) -> jwt.PyJWKClient:
    # Bounded cache; PyJWT refreshes on an unknown kid to support key rotation.
    return jwt.PyJWKClient(
        f"{issuer}/.well-known/jwks.json",
        lifespan=300,
        timeout=8,
        headers={"User-Agent": "Serenity/1.0", "Accept": "application/json"},
    )


def _authorized_parties() -> set[str]:
    """Production origins are explicit; dev origins come from Replit config."""
    parties = {
        origin.strip() for origin in
        os.getenv("SERENITY_AUTHORIZED_PARTIES", "").split(",") if origin.strip()
    }
    if os.getenv("SERENITY_DEV") == "1":
        parties.update(
            f"https://{host.strip()}" for host in
            os.getenv("REPLIT_DOMAINS", "").split(",") if host.strip()
        )
        domain = os.getenv("REPLIT_DEV_DOMAIN")
        if domain:
            parties.add(f"https://{domain}")
    return parties


def verify_clerk_token(token: str) -> tuple[str, str] | None:
    """Verify RS256 signature and claims before checking live session status."""
    try:
        issuer = configured_clerk_issuer()
        header = jwt.get_unverified_header(token)
        if header.get("alg") != "RS256" or not isinstance(header.get("kid"), str):
            return None
        key = _jwks_client(issuer).get_signing_key_from_jwt(token)
        claims = jwt.decode(
            token, key.key, algorithms=["RS256"], issuer=issuer,
            options={"require": ["iss", "exp", "nbf", "iat", "sub", "sid"]},
        )
        for field in ("exp", "nbf", "iat"):
            if type(claims[field]) is not int:
                return None
        for field in ("sub", "sid"):
            if not isinstance(claims[field], str) or not re.fullmatch(
                r"[A-Za-z0-9_-]+", claims[field]
            ):
                return None
        # This is a browser-only exchange: require azp, including when the
        # caller omits Origin. Never build the allowlist from request headers.
        if not isinstance(claims.get("azp"), str) or claims["azp"] not in _authorized_parties():
            return None
    except (jwt.PyJWKClientConnectionError, urllib.error.URLError, TimeoutError) as exc:
        raise ClerkUnavailableError("Clerk signing keys unavailable") from exc
    except ClerkUnavailableError:
        raise
    except (jwt.PyJWTError, ValueError, TypeError, OSError):
        return None

    if not _live_clerk_session(claims["sid"], claims["sub"]):
        return None
    return claims["sub"], claims["sid"]


def _live_clerk_session(session_id: str, user_id: str) -> bool:
    """Fail closed on network errors, revoked sessions, or owner mismatch."""
    secret = os.getenv("CLERK_SECRET_KEY")
    if not secret:
        raise ClerkUnavailableError("Clerk credentials are not configured")
    request = urllib.request.Request(
        f"https://api.clerk.com/v1/sessions/{session_id}",
        headers={
            "Authorization": f"Bearer {secret}",
            "User-Agent": "Serenity/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            session = json.loads(response.read())
    except urllib.error.HTTPError as error:
        logging.getLogger(__name__).warning(
            "Clerk session lookup failed with HTTP %s", error.code
        )
        if error.code >= 500 or error.code == 429:
            raise ClerkUnavailableError("Clerk session lookup unavailable") from error
        return False
    except (urllib.error.URLError, TimeoutError, ValueError):
        logging.getLogger(__name__).warning("Clerk session lookup unavailable")
        raise ClerkUnavailableError("Clerk session lookup unavailable")

    return (isinstance(session, dict) and session.get("status") == "active"
            and session.get("user_id") == user_id)


def bearer_token(request: Request) -> str | None:
    authorization = request.headers.get("Authorization", "")
    scheme, _, token = authorization.partition(" ")
    return token if scheme.lower() == "bearer" and token else None