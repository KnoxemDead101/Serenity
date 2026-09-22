"""
Shared validation rules.

These are plain functions so they can be reused by any schema (accounts
now; transactions, bills and debts later) and tested on their own.

Each function either RETURNS a cleaned value or RAISES ValueError with a
message a human can read. Pydantic (see schemas/) turns that ValueError
into a 422 error response for the API caller.

Remember: the browser can also check inputs, but that is only for a
nicer user experience. These backend checks are the ones that count.
"""

from decimal import Decimal

MAX_TEXT_LENGTH = 100

# A sanity limit that also keeps cents safely inside SQLite's integer range.
MAX_MONEY = Decimal("1000000000000")  # one trillion dollars


def require_text(value: str, field_name: str, max_length: int = MAX_TEXT_LENGTH) -> str:
    """Strip spaces and make sure something is left, and it isn't too long."""
    cleaned = value.strip()
    if not cleaned:
        raise ValueError(f"{field_name} is required")
    if len(cleaned) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer")
    return cleaned


def optional_text(value: str | None, max_length: int = 500) -> str | None:
    """Turn blank strings into None so the database stores 'nothing', not ''."""
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > max_length:
        raise ValueError(f"must be {max_length} characters or fewer")
    return cleaned


def require_choice(value: str, allowed: list[str], field_name: str) -> str:
    """Make sure the value is one of the allowed options."""
    if value not in allowed:
        options = ", ".join(allowed)
        raise ValueError(f"{field_name} must be one of: {options}")
    return value


def validate_money(value: Decimal, field_name: str) -> Decimal:
    """
    Make sure a dollar amount has at most 2 decimal places.

    We reject 10.005 instead of rounding it, because silently changing a
    financial number is worse than asking the user to fix it.
    """
    if not value.is_finite():
        raise ValueError(f"{field_name} must be a real number")
    if abs(value) > MAX_MONEY:
        raise ValueError(f"{field_name} is too large")
    two_places = value.quantize(Decimal("0.01"))
    if value != two_places:
        raise ValueError(f"{field_name} can have at most 2 decimal places")
    return two_places
