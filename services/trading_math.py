"""Exact, server-owned mathematics for hypothetical investments and futures.

Specifications are supplied by the owner-scoped registry route, not by the
browser. These computations do not create trades or change account balances.
All money is rounded half-up *once* at the output boundary. Ratios use
unrounded facts so displayed money rounding cannot distort their values.
"""

from decimal import Decimal, ROUND_HALF_UP, localcontext

from schemas.trading_math import CalculationRead, CalculationRequest, bounded_decimal

CENT = Decimal("0.01")
RATIO_STEP = Decimal("0.00000001")


def _money(value: Decimal) -> Decimal:
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def _ratio(value: Decimal) -> Decimal:
    return value.quantize(RATIO_STEP, rounding=ROUND_HALF_UP)


def calculate_trade(
    request: CalculationRequest, *, asset_type: str,
    tick_size: Decimal, point_value: Decimal,
) -> CalculationRead:
    """Calculate a *hypothetical* outcome using an immutable specification.

    The endpoint must independently verify specification ownership before
    calling this function. Price difference is exit minus entry, while points
    and ticks are signed in the position's direction. Fees represent total
    trade fees, not per-contract fees. Planned risk and reward exclude fees;
    realized R uses net P&L (including fees) over exact planned dollar risk.
    """
    if asset_type not in {"STOCK", "ETF", "FUTURE"}:
        raise ValueError("Unsupported instrument type")
    if not isinstance(tick_size, Decimal) or not isinstance(point_value, Decimal):
        raise ValueError("Instrument specification must use exact Decimal values")

    with localcontext() as context:
        context.prec = 80
        bounded_decimal(tick_size, "Tick size", positive=True)
        bounded_decimal(point_value, "Point value", positive=True)
        if asset_type in {"STOCK", "ETF"} and point_value != 1:
            raise ValueError("Stocks and ETFs must have a point value of 1")
        if asset_type == "FUTURE" and request.quantity != request.quantity.to_integral_value():
            raise ValueError("Futures contract quantity must be a whole number")

        prices = (
            request.entry_price, request.exit_price, request.stop_price,
            request.target_price,
        )
        if asset_type in {"STOCK", "ETF"} and any(
            price is not None and price < 0 for price in prices
        ):
            raise ValueError("Stocks and ETFs cannot have negative prices")
        for price in prices:
            if price is not None and (price / tick_size) != (price / tick_size).to_integral_value():
                raise ValueError("Prices must align with the instrument tick size")

        sign = Decimal(1) if request.direction == "LONG" else Decimal(-1)
        entry = request.entry_price
        quantity = request.quantity
        value_per_point = point_value * quantity

        risk_points = risk_ticks = risk_dollars = None
        raw_risk_dollars = None
        if request.stop_price is not None:
            raw_risk_points = (entry - request.stop_price) * sign
            if raw_risk_points <= 0:
                raise ValueError("Stop must be strictly against the trade direction")
            risk_points = raw_risk_points
            risk_ticks = raw_risk_points / tick_size
            raw_risk_dollars = raw_risk_points * value_per_point
            risk_dollars = _money(raw_risk_dollars)

        reward_points = reward_ticks = reward_dollars = None
        raw_reward_dollars = None
        if request.target_price is not None:
            raw_reward_points = (request.target_price - entry) * sign
            if raw_reward_points <= 0:
                raise ValueError("Target must be strictly in the profitable direction")
            reward_points = raw_reward_points
            reward_ticks = raw_reward_points / tick_size
            raw_reward_dollars = raw_reward_points * value_per_point
            reward_dollars = _money(raw_reward_dollars)

        planned_rr = (
            _ratio(raw_reward_dollars / raw_risk_dollars)
            if raw_reward_dollars is not None and raw_risk_dollars is not None
            else None
        )

        price_difference = points = ticks = gross_pnl = net_pnl = realized_r = None
        if request.exit_price is not None:
            price_difference = request.exit_price - entry
            points = price_difference * sign
            ticks = points / tick_size
            raw_gross = points * value_per_point
            raw_net = raw_gross - request.fees
            gross_pnl = _money(raw_gross)
            net_pnl = _money(raw_net)
            if raw_risk_dollars is not None:
                realized_r = _ratio(raw_net / raw_risk_dollars)

        return CalculationRead(
            price_difference=price_difference,
            points=points,
            ticks=ticks,
            gross_pnl=gross_pnl,
            fees=request.fees,
            net_pnl=net_pnl,
            risk_points=risk_points,
            risk_ticks=risk_ticks,
            risk_dollars=risk_dollars,
            reward_points=reward_points,
            reward_ticks=reward_ticks,
            reward_dollars=reward_dollars,
            planned_rr=planned_rr,
            realized_r=realized_r,
        )