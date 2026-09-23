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

from decimal import Decimal, ROUND_HALF_UP

CENTS_PER_DOLLAR = 100
MILLI_PERCENT_PER_PERCENT = 1000
QUANTITY_UNITS_PER_WHOLE = 100_000_000


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


def round_half_up_division(numerator: int, denominator: int) -> int:
    """Divide integers and round halves away from zero."""
    if denominator <= 0:
        raise ValueError("Denominator must be positive")
    return int(
        (Decimal(numerator) / Decimal(denominator)).quantize(
            Decimal("1"), rounding=ROUND_HALF_UP
        )
    )


def percent_to_milli(rate: Decimal) -> int:
    """Convert a percentage such as 6.875 into 6875 milli-percent units."""
    units = rate * MILLI_PERCENT_PER_PERCENT
    if units != units.to_integral_value():
        raise ValueError(f"{rate} has more than 3 decimal places")
    return int(units)


def milli_to_percent(value: int) -> Decimal:
    """Convert milli-percent units back to an exact percentage."""
    return (Decimal(value) / MILLI_PERCENT_PER_PERCENT).quantize(Decimal("0.001"))


def quantity_to_units(quantity: Decimal) -> int:
    """Convert a quantity into integer units with eight decimal places."""
    units = quantity * QUANTITY_UNITS_PER_WHOLE
    if units != units.to_integral_value():
        raise ValueError(f"{quantity} has more than 8 decimal places")
    return int(units)


def units_to_quantity(units: int) -> Decimal:
    """Convert integer quantity units back to eight-decimal precision."""
    return (Decimal(units) / QUANTITY_UNITS_PER_WHOLE).quantize(
        Decimal("0.00000001")
    )
