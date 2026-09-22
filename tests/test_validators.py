"""Tests for utils/validators.py."""

from decimal import Decimal

import pytest

from utils.validators import optional_text, require_choice, require_text, validate_money


def test_require_text_strips_spaces():
    assert require_text("  Checking  ", "Name") == "Checking"


def test_require_text_rejects_blank():
    with pytest.raises(ValueError, match="Name is required"):
        require_text("   ", "Name")


def test_require_text_rejects_too_long():
    with pytest.raises(ValueError):
        require_text("x" * 101, "Name")


def test_optional_text_turns_blank_into_none():
    assert optional_text("   ") is None
    assert optional_text(None) is None
    assert optional_text(" Chase ") == "Chase"


def test_require_choice():
    assert require_choice("Personal", ["Personal", "Business"], "Classification") == "Personal"
    with pytest.raises(ValueError):
        require_choice("personal", ["Personal", "Business"], "Classification")  # case matters


def test_validate_money_accepts_two_decimal_places():
    assert validate_money(Decimal("10.5"), "Amount") == Decimal("10.50")
    assert validate_money(Decimal("-3.25"), "Amount") == Decimal("-3.25")
    assert validate_money(Decimal("7.500"), "Amount") == Decimal("7.50")  # trailing zero is fine


def test_validate_money_rejects_fractions_of_a_cent():
    with pytest.raises(ValueError, match="2 decimal places"):
        validate_money(Decimal("10.005"), "Amount")


def test_validate_money_rejects_nan_and_huge_values():
    with pytest.raises(ValueError):
        validate_money(Decimal("NaN"), "Amount")
    with pytest.raises(ValueError):
        validate_money(Decimal("1e20"), "Amount")
