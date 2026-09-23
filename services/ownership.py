"""Validation helpers for user-scoped financial records."""

OWNER_ID_MAX_LENGTH = 255


class MissingOwnerError(ValueError):
    """A service was called without a usable owner id."""


def require_owner_id(owner_id: str | None) -> str:
    """Return a valid owner id, refusing missing, blank, or oversized ids."""
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise MissingOwnerError("An owner id is required for financial records.")
    if len(owner_id) > OWNER_ID_MAX_LENGTH:
        raise MissingOwnerError("Owner id is too long.")
    return owner_id