"""Phase 1 hypothetical calculator precision, validation and math."""

from decimal import Decimal, localcontext

import pytest
from pydantic import ValidationError

from schemas.trading_math import CalculationRequest
from services.trading_math import calculate_trade


def request(**changes):
    payload = {
        "specification_id": 2,
        "direction": "LONG",
        "quantity": "1",
        "entry_price": "100",
    }
    payload.update(changes)
    return CalculationRequest(**payload)


def compute(*, asset_type="FUTURE", tick_size="0.25", point_value="50", **fields):
    return calculate_trade(
        request(**fields), asset_type=asset_type,
        tick_size=Decimal(tick_size), point_value=Decimal(point_value),
    )


def test_long_mini_multiple_contracts_uses_instrument_point_value_and_total_fees():
    result = compute(
        quantity="3", entry_price="5000", exit_price="5004.25",
        stop_price="4997.50", target_price="5005", fees="12.50",
    )
    assert result.price_difference == Decimal("4.25")
    assert result.points == Decimal("4.25")
    assert result.ticks == Decimal("17")
    assert result.gross_pnl == Decimal("637.50")
    assert result.fees == Decimal("12.50")
    assert result.net_pnl == Decimal("625.00")
    assert result.risk_points == Decimal("2.50")
    assert result.risk_ticks == Decimal("10")
    assert result.risk_dollars == Decimal("375.00")
    assert result.reward_points == Decimal("5")
    assert result.reward_ticks == Decimal("20")
    assert result.reward_dollars == Decimal("750.00")
    assert result.planned_rr == Decimal("2")
    assert result.realized_r == Decimal("1.66666667")


def test_micro_uses_specification_not_mini_hardcoding():
    kwargs = {"quantity": "3", "entry_price": "5000", "exit_price": "5004.25"}
    mini = compute(point_value="50", **kwargs)
    micro = compute(point_value="5", **kwargs)
    assert mini.points == micro.points == Decimal("4.25")
    assert mini.ticks == micro.ticks == Decimal("17")
    assert mini.gross_pnl == Decimal("637.50")
    assert micro.gross_pnl == Decimal("63.75")


def test_short_profitable_and_losing_exit_signs_and_fees():
    win = compute(direction="SHORT", quantity="2", entry_price="100",
                  exit_price="98.75", stop_price="101", target_price="98",
                  fees="1")
    assert win.price_difference == Decimal("-1.25")
    assert win.points == Decimal("1.25")
    assert win.ticks == Decimal("5")
    assert win.gross_pnl == Decimal("125.00")
    assert win.net_pnl == Decimal("124.00")
    assert win.risk_dollars == Decimal("100.00")
    assert win.reward_dollars == Decimal("200.00")
    assert win.planned_rr == Decimal("2")
    assert win.realized_r == Decimal("1.24")

    loss = compute(direction="SHORT", quantity="2", entry_price="100",
                   exit_price="101.25", stop_price="101.50", fees="0.50")
    assert loss.price_difference == Decimal("1.25")
    assert loss.points == Decimal("-1.25")
    assert loss.ticks == Decimal("-5")
    assert loss.gross_pnl == Decimal("-125.00")
    assert loss.net_pnl == Decimal("-125.50")
    assert loss.realized_r == Decimal("-0.83666667")


def test_fractional_stock_share_is_exact_and_negative_exit_is_disallowed():
    result = compute(
        asset_type="STOCK", tick_size="0.00000001", point_value="1",
        quantity="0.147392", entry_price="10.00000000",
        exit_price="11.00000000", stop_price="9.00000000",
        target_price="12.00000000", fees="0",
    )
    assert result.gross_pnl == Decimal("0.15")
    assert result.net_pnl == Decimal("0.15")
    assert result.risk_dollars == Decimal("0.15")
    assert result.reward_dollars == Decimal("0.29")
    assert result.planned_rr == Decimal("2")
    assert result.realized_r == Decimal("1")
    with pytest.raises(ValueError, match="negative prices"):
        compute(asset_type="ETF", tick_size="0.01", point_value="1",
                entry_price="0", exit_price="-1")


def test_rounding_happens_only_at_output_not_in_ratio():
    result = compute(
        asset_type="ETF", tick_size="0.00000001", point_value="1",
        quantity="0.147392", entry_price="10.00000000",
        exit_price="11.00000000", stop_price="9.00000000",
        target_price="12.00000000", fees="0.01",
    )
    assert result.net_pnl == Decimal("0.14")
    # Ratio derives from exact .147392 minus .01, not displayed .14/.15.
    assert result.realized_r == Decimal("0.93215371")
    assert result.planned_rr == Decimal("2")


def test_half_cent_rounds_away_from_zero_exactly_once():
    pos = compute(asset_type="STOCK", tick_size="0.001", point_value="1",
                  quantity="5", entry_price="10", exit_price="10.001")
    neg = compute(asset_type="STOCK", tick_size="0.001", point_value="1",
                  quantity="5", entry_price="10", exit_price="9.999")
    assert pos.gross_pnl == Decimal("0.01")
    assert neg.gross_pnl == Decimal("-0.01")


def test_planned_only_has_no_actual_pnl():
    result = compute(entry_price="5000", stop_price="4998", target_price="5004")
    for field in ("price_difference", "points", "ticks", "gross_pnl",
                  "net_pnl", "realized_r"):
        assert getattr(result, field) is None
    assert result.fees == 0
    assert result.risk_dollars == Decimal("100.00")
    assert result.reward_dollars == Decimal("200.00")
    assert result.planned_rr == Decimal("2")
    assert result.model_dump(mode="json")["risk_dollars"] == "100.00"
    assert result.model_dump(mode="json")["net_pnl"] is None


def test_realized_r_requires_stop_even_when_exit_exists():
    result = compute(exit_price="101", fees="2")
    assert result.net_pnl == Decimal("48.00")
    assert result.realized_r is None
    assert result.planned_rr is None


@pytest.mark.parametrize("fields,message", [
    ({"stop_price": "100"}, "Stop"),
    ({"stop_price": "100.25"}, "Stop"),
    ({"target_price": "100"}, "Target"),
    ({"target_price": "99.75"}, "Target"),
    ({"direction": "SHORT", "stop_price": "99.75"}, "Stop"),
    ({"direction": "SHORT", "target_price": "100.25"}, "Target"),
])
def test_wrong_side_or_zero_risk_and_reward_are_refused(fields, message):
    with pytest.raises(ValueError, match=message):
        compute(**fields)


@pytest.mark.parametrize("fields", [
    {"entry_price": "100.125"},
    {"exit_price": "101.01"},
    {"stop_price": "99.99"},
    {"target_price": "100.99"},
])
def test_futures_prices_must_align_with_tick_grid(fields):
    with pytest.raises(ValueError, match="tick"):
        compute(**fields)


def test_negative_futures_prices_can_align_to_tick_grid():
    result = compute(direction="SHORT", entry_price="-1.25",
                     exit_price="-2.25", stop_price="-0.75",
                     target_price="-2.50")
    assert result.gross_pnl == Decimal("50.00")
    assert result.planned_rr == Decimal("2.5")


@pytest.mark.parametrize("fields", [
    {"specification_id": 0}, {"specification_id": -3},
    {"direction": "FLAT"}, {"quantity": "0"}, {"quantity": "-1"},
    {"quantity": "0.000000001"}, {"quantity": "1000000001"},
    {"entry_price": "1000000000.01"}, {"exit_price": "0.000000001"},
    {"stop_price": "NaN"}, {"target_price": "Infinity"},
    {"fees": "-0.01"}, {"fees": "1.001"}, {"fees": "1000000001"},
    {"unrecognized": "forbid"},
])
def test_schema_refuses_invalid_payloads(fields):
    with pytest.raises(ValidationError):
        request(**fields)


@pytest.mark.parametrize("asset_type,tick_size,point_value,fields,match", [
    ("OPTION", "0.01", "1", {}, "Unsupported"),
    ("STOCK", "0.01", "50", {}, "point value"),
    ("ETF", "0.01", "0.5", {}, "point value"),
    ("STOCK", "0.01", "1", {"entry_price": "-1"}, "negative prices"),
    ("FUTURE", "0.25", "50", {"quantity": "0.5"}, "whole number"),
    ("FUTURE", "0", "50", {}, "Tick size"),
    ("FUTURE", "0.000000001", "50", {}, "Tick size"),
    ("FUTURE", "0.25", "0", {}, "Point value"),
    ("FUTURE", "0.25", "NaN", {}, "Point value"),
    ("FUTURE", "0.25", "1000000001", {}, "Point value"),
])
def test_specification_and_asset_invariants(asset_type, tick_size, point_value, fields, match):
    with pytest.raises(ValueError, match=match):
        compute(asset_type=asset_type, tick_size=tick_size,
                point_value=point_value, **fields)


def test_unmodified_old_specification_arguments_reproduce_old_result():
    req = request(entry_price="5000", exit_price="5001", stop_price="4999")
    original = calculate_trade(req, asset_type="FUTURE", tick_size=Decimal("0.25"),
                               point_value=Decimal("50"))
    new_version = calculate_trade(req, asset_type="FUTURE", tick_size=Decimal("0.25"),
                                  point_value=Decimal("5"))
    replay = calculate_trade(req, asset_type="FUTURE", tick_size=Decimal("0.25"),
                             point_value=Decimal("50"))
    assert original == replay
    assert new_version.gross_pnl == Decimal("5.00")
    assert original.gross_pnl == Decimal("50.00")


def test_large_values_are_exact_independent_of_caller_decimal_precision():
    req = request(quantity="1000000000", entry_price="1000000000",
                  exit_price="999999999.99999999", fees="0")
    with localcontext() as context:
        context.prec = 6
        result = calculate_trade(req, asset_type="FUTURE",
                                 tick_size=Decimal("0.00000001"),
                                 point_value=Decimal("1000000000"))
    assert result.gross_pnl == Decimal("-10000000000.00")
    assert result.points == Decimal("-0.00000001")