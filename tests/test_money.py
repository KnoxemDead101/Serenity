"""Tests for utils/money.py: the dollars <-> cents rule."""

from decimal import Decimal

import pytest

from utils.money import (
    cents_to_dollars,
    dollars_to_cents,
    milli_to_percent,
    percent_to_milli,
    quantity_to_units,
    round_half_up_division,
    units_to_quantity,
)


def test_dollars_to_cents():
    assert dollars_to_cents(Decimal("12.34")) == 1234
    assert dollars_to_cents(Decimal("0")) == 0
    assert dollars_to_cents(Decimal("-5.10")) == -510
    assert dollars_to_cents(Decimal("1000000")) == 100_000_000


def test_cents_to_dollars():
    assert cents_to_dollars(1234) == Decimal("12.34")
    assert cents_to_dollars(-510) == Decimal("-5.10")
    assert str(cents_to_dollars(500)) == "5.00"  # always 2 decimal places


def test_round_trip_is_exact():
    # The classic float bug: 0.1 + 0.2 != 0.3. With cents it's exact.
    total = dollars_to_cents(Decimal("0.10")) + dollars_to_cents(Decimal("0.20"))
    assert cents_to_dollars(total) == Decimal("0.30")


def test_refuses_fractions_of_a_cent():
    with pytest.raises(ValueError):
        dollars_to_cents(Decimal("1.005"))


def test_scaled_financial_units_are_exact():
    assert percent_to_milli(Decimal("6.875")) == 6875
    assert milli_to_percent(6875) == Decimal("6.875")
    assert quantity_to_units(Decimal("0.12345678")) == 12_345_678
    assert units_to_quantity(12_345_678) == Decimal("0.12345678")
    assert round_half_up_division(100, 12) == 8
