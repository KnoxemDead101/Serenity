"""Offline production origin readiness check; never prints configuration values."""

import os
import re
import sys
from urllib.parse import urlsplit


def valid_production_origin(origin: str) -> bool:
    """Require a canonical HTTPS public DNS origin, not a preview or URL path."""
    try:
        parsed = urlsplit(origin)
        host = parsed.hostname or ""
        port = parsed.port
        labels = host.split(".")
        return (
            parsed.scheme == "https"
            and len(labels) > 1
            and all(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
                    for label in labels)
            and not host.replace(".", "").isdigit()
            and not any(host == suffix or host.endswith("." + suffix)
                        for suffix in ("localhost", "local", "test", "invalid", "replit.dev"))
            and not parsed.username and not parsed.password
            and (port is None or 0 < port <= 65535 and port != 443)
            and origin == "https://" + host + (f":{port}" if port else "")
        )
    except ValueError:
        return False


def check_auth(environ=None) -> int:
    env = os.environ if environ is None else environ
    if env.get("SERENITY_DEV") == "1":
        print("AUTH BLOCKED: SERENITY_DEV must not be enabled in production.")
        return 1
    expected = env.get("SERENITY_CHECK_PUBLISHED_ORIGIN", "").strip()
    if not valid_production_origin(expected):
        print("AUTH BLOCKED: set SERENITY_CHECK_PUBLISHED_ORIGIN to the exact "
              "HTTPS origin confirmed in deployment metadata.")
        return 1
    parties = [part.strip() for part in
               env.get("SERENITY_AUTHORIZED_PARTIES", "").split(",")]
    if not all(valid_production_origin(part) for part in parties):
        print("AUTH BLOCKED: SERENITY_AUTHORIZED_PARTIES must contain only exact "
              "production HTTPS origins; no blanks, paths, wildcards or preview domains.")
        return 1
    if expected not in parties:
        print("AUTH BLOCKED: the confirmed published origin is missing from "
              "SERENITY_AUTHORIZED_PARTIES.")
        return 1
    print("AUTH CONFIG OK: confirmed published origin is explicitly allowed. "
          "This is not a live sign-in test. Verify managed Clerk sign-in on that "
          "origin before entering financial records.")
    return 0


if __name__ == "__main__":
    sys.exit(check_auth())