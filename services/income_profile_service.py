"""Owner-scoped income profile CRUD and exact projection calculations."""

from decimal import Decimal
from fractions import Fraction
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.income_profile import IncomeProfile
from schemas.income_profile import (
    IncomeCalculation,
    IncomeProfileCreate,
    IncomeProfileRead,
    IncomeProfileUpdate,
    IncomeSummary,
)
from services.ownership import require_owner_id
from utils.choices import (
    ACCOUNT_CLASSIFICATIONS,
    INCOME_TYPES,
    PAY_FREQUENCIES,
    PAY_PERIODS_PER_YEAR,
)
from utils.money import cents_to_dollars, dollars_to_cents, round_half_up_division

WEEKS_PER_YEAR = 52


def _round(value: Fraction) -> int:
    return round_half_up_division(value.numerator, value.denominator)


def _hours_to_units(value: Decimal | None) -> int | None:
    if value is None:
        return None
    units = value * 100
    if units != units.to_integral_value():
        raise ValueError(f"{value} has more than 2 decimal places")
    return int(units)


def _units_to_hours(value: int | None) -> Decimal | None:
    return (Decimal(value) / 100).quantize(Decimal("0.01")) if value is not None else None


def _money(cents: int | None) -> Decimal | None:
    return cents_to_dollars(cents) if cents is not None else None


def is_projected(profile: IncomeProfile) -> bool:
    return profile.income_type != "Variable"


def _annual_gross(profile: IncomeProfile) -> Fraction | None:
    if not is_projected(profile):
        return None
    if profile.income_type == "Hourly":
        return Fraction(profile.hourly_rate_cents * profile.expected_hours_hundredths * 52, 100)
    if profile.income_type == "Salary":
        return Fraction(profile.annual_salary_cents)
    return Fraction(
        profile.amount_per_period_cents * PAY_PERIODS_PER_YEAR[profile.pay_frequency]
    )


def _annual_net(profile: IncomeProfile) -> Fraction | None:
    if not is_projected(profile) or profile.expected_net_per_period_cents is None:
        return None
    return Fraction(
        profile.expected_net_per_period_cents * PAY_PERIODS_PER_YEAR[profile.pay_frequency]
    )


def calculate(profile: IncomeProfile) -> IncomeCalculation:
    annual = _annual_gross(profile)
    if annual is None:
        return IncomeCalculation(
            projected=False,
            basis="variable income is not projected",
            gross_per_period=None,
            gross_weekly=None,
            gross_monthly=None,
            gross_annual=None,
            standard_weekly_gross=None,
            net_per_period=None,
            net_monthly=None,
            net_annual=None,
        )
    periods = PAY_PERIODS_PER_YEAR[profile.pay_frequency]
    basis = (
        "hourly rate x expected hours per week x 52 weeks"
        if profile.income_type == "Hourly"
        else "annual salary divided into pay periods"
        if profile.income_type == "Salary"
        else f"amount per paycheck x {periods} paychecks a year"
    )
    standard = None
    if profile.income_type == "Hourly" and profile.standard_hours_hundredths is not None:
        standard = cents_to_dollars(_round(Fraction(
            profile.hourly_rate_cents * profile.standard_hours_hundredths, 100
        )))
    net = _annual_net(profile)
    return IncomeCalculation(
        projected=True,
        basis=basis,
        gross_per_period=cents_to_dollars(_round(annual / periods)),
        gross_weekly=cents_to_dollars(_round(annual / 52)),
        gross_monthly=cents_to_dollars(_round(annual / 12)),
        gross_annual=cents_to_dollars(_round(annual)),
        standard_weekly_gross=standard,
        net_per_period=_money(profile.expected_net_per_period_cents),
        net_monthly=cents_to_dollars(_round(net / 12)) if net is not None else None,
        net_annual=cents_to_dollars(_round(net)) if net is not None else None,
    )


def summarize(profiles: Iterable[IncomeProfile]) -> IncomeSummary:
    active = [item for item in profiles if item.active is not False]
    projected = [item for item in active if is_projected(item)]
    with_net = [item for item in projected if item.expected_net_per_period_cents is not None]
    annual = sum((_annual_gross(item) for item in projected), Fraction(0))
    net = sum((_annual_net(item) for item in with_net), Fraction(0))
    return IncomeSummary(
        active_count=len(active),
        projected_count=len(projected),
        variable_count=len(active) - len(projected),
        gross_monthly=cents_to_dollars(_round(annual / 12)),
        gross_annual=cents_to_dollars(_round(annual)),
        net_profile_count=len(with_net),
        net_monthly=cents_to_dollars(_round(net / 12)) if with_net else None,
        net_annual=cents_to_dollars(_round(net)) if with_net else None,
        net_is_partial=bool(with_net) and len(with_net) < len(projected),
    )


def _apply(profile: IncomeProfile, data: IncomeProfileCreate) -> None:
    profile.name = data.name
    profile.income_type = data.income_type
    profile.classification = data.classification
    profile.pay_frequency = data.pay_frequency
    profile.hourly_rate_cents = dollars_to_cents(data.hourly_rate) if data.hourly_rate is not None else None
    profile.standard_hours_hundredths = _hours_to_units(data.standard_hours_per_week)
    profile.expected_hours_hundredths = _hours_to_units(data.expected_hours_per_week)
    profile.annual_salary_cents = dollars_to_cents(data.annual_salary) if data.annual_salary is not None else None
    profile.amount_per_period_cents = dollars_to_cents(data.amount_per_period) if data.amount_per_period is not None else None
    profile.expected_net_per_period_cents = (
        dollars_to_cents(data.expected_net_per_period)
        if data.expected_net_per_period is not None else None
    )
    profile.notes = data.notes


def create_income_profile(db: Session, data: IncomeProfileCreate, owner_id: str) -> IncomeProfile:
    profile = IncomeProfile(owner_id=require_owner_id(owner_id), active=True)
    _apply(profile, data)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def list_income_profiles(db: Session, owner_id: str) -> list[IncomeProfile]:
    return list(db.scalars(
        select(IncomeProfile)
        .where(IncomeProfile.owner_id == require_owner_id(owner_id))
        .order_by(IncomeProfile.active.desc(), IncomeProfile.name, IncomeProfile.id)
    ))


def get_income_profile(db: Session, profile_id: int, owner_id: str) -> IncomeProfile | None:
    return db.scalar(select(IncomeProfile).where(
        IncomeProfile.id == profile_id,
        IncomeProfile.owner_id == require_owner_id(owner_id),
    ))


def update_income_profile(
    db: Session, profile: IncomeProfile, data: IncomeProfileUpdate
) -> IncomeProfile:
    _apply(profile, data)
    db.commit()
    db.refresh(profile)
    return profile


def set_income_profile_active(
    db: Session, profile: IncomeProfile, active: bool
) -> IncomeProfile:
    profile.active = active
    db.commit()
    db.refresh(profile)
    return profile


def get_income_summary(db: Session, owner_id: str) -> IncomeSummary:
    return summarize(list_income_profiles(db, owner_id))


def get_income_options() -> dict[str, list[str]]:
    return {
        "income_types": INCOME_TYPES,
        "pay_frequencies": PAY_FREQUENCIES,
        "classifications": ACCOUNT_CLASSIFICATIONS,
    }


def to_income_profile_read(profile: IncomeProfile) -> IncomeProfileRead:
    return IncomeProfileRead(
        id=profile.id,
        name=profile.name,
        income_type=profile.income_type,
        classification=profile.classification,
        pay_frequency=profile.pay_frequency,
        hourly_rate=_money(profile.hourly_rate_cents),
        standard_hours_per_week=_units_to_hours(profile.standard_hours_hundredths),
        expected_hours_per_week=_units_to_hours(profile.expected_hours_hundredths),
        annual_salary=_money(profile.annual_salary_cents),
        amount_per_period=_money(profile.amount_per_period_cents),
        expected_net_per_period=_money(profile.expected_net_per_period_cents),
        notes=profile.notes,
        active=profile.active,
        calculated=calculate(profile),
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )