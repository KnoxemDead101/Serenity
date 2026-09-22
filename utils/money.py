"""
Money helpers.

WHY THIS FILE EXISTS
--------------------
Computers store normal decimal numbers ("floats") in binary, and many
decimal values can't be represented exactly. For example, in Python:

    >>> 0.10 + 0.20
    0.30000000000000004

That tiny error is unacceptable in a finance app. Serenity avoids it with
one simple rule:

    Money is STORED as a whole number of cents (an int).
    Money is ENTERED and DISPLAYED as dollars (a Decimal).

$12.34 is stored as 1234. Adding integers is always exact.

The two functions below are the only place that converts between the
two forms, so the rule lives in one file.
"""

from decimal import Decimal

CENTS_PER_DOLLAR = 100


def dollars_to_cents(dollars: Decimal) -> int:
    """
    Convert a dollar amount like Decimal("12.34") into cents (1234).

    The caller must pass a value with at most 2 decimal places.
    Validation (see utils/validators.py) guarantees that before this
    function is ever called, so we refuse to silently round here.
    """
    cents = dollars * CENTS_PER_DOLLAR
    if cents != cents.to_integral_value():
        raise ValueError(f"{dollars} has more than 2 decimal places")
    return int(cents)


def cents_to_dollars(cents: int) -> Decimal:
    """Convert cents (1234) back into dollars (Decimal("12.34"))."""
    return (Decimal(cents) / CENTS_PER_DOLLAR).quantize(Decimal("0.01"))
