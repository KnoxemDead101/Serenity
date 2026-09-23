"""Income profiles are owner-scoped plans, not balance-changing transactions."""

from decimal import Decimal

from conftest import TEST_OWNER_ID
from schemas.income_profile import IncomeProfileCreate
from services import income_profile_service as service


def hourly(**overrides):
    values = {
        "name": "Warehouse job",
        "income_type": "Hourly",
        "classification": "Personal",
        "pay_frequency": "Biweekly",
        "hourly_rate": "20.00",
        "standard_hours_per_week": "40.00",
        "expected_hours_per_week": "40.00",
    }
    values.update(overrides)
    return IncomeProfileCreate(**values)


def test_hourly_calculation_uses_yearly_basis_and_integer_storage(db):
    profile = service.create_income_profile(db, hourly(), TEST_OWNER_ID)
    assert profile.hourly_rate_cents == 2000
    assert profile.expected_hours_hundredths == 4000
    result = service.to_income_profile_read(profile)
    assert result.calculated.gross_per_period == Decimal("1600.00")
    assert result.calculated.gross_weekly == Decimal("800.00")
    assert result.calculated.gross_monthly == Decimal("3466.67")
    assert result.calculated.gross_annual == Decimal("41600.00")
    assert result.calculated.standard_weekly_gross == Decimal("800.00")


def test_variable_income_is_retained_but_not_projected(db):
    profile = service.create_income_profile(
        db,
        IncomeProfileCreate(
            name="Commission",
            income_type="Variable",
            amount_per_period="900.00",
        ),
        TEST_OWNER_ID,
    )
    result = service.to_income_profile_read(profile)
    assert result.calculated.projected is False
    assert result.calculated.gross_monthly is None
    summary = service.get_income_summary(db, TEST_OWNER_ID)
    assert summary.active_count == 1
    assert summary.variable_count == 1
    assert summary.gross_annual == Decimal("0.00")


def test_profiles_are_owner_scoped_and_soft_deactivation_excludes_totals(db):
    profile = service.create_income_profile(db, hourly(), "owner-a")
    assert service.get_income_profile(db, profile.id, "owner-b") is None
    assert service.list_income_profiles(db, "owner-b") == []
    service.set_income_profile_active(db, profile, False)
    assert service.get_income_summary(db, "owner-a").active_count == 0
    assert service.get_income_profile(db, profile.id, "owner-a").active is False


def test_irrelevant_type_fields_are_cleared_when_profile_is_changed(db):
    profile = service.create_income_profile(db, hourly(), TEST_OWNER_ID)
    salary = IncomeProfileCreate(
        name="Salary role",
        income_type="Salary",
        pay_frequency="Monthly",
        annual_salary="60000.00",
        hourly_rate="99.00",
        expected_hours_per_week="30",
    )
    service.update_income_profile(db, profile, salary)
    assert profile.annual_salary_cents == 6_000_000
    assert profile.hourly_rate_cents is None
    assert profile.expected_hours_hundredths is None


def test_income_api_export_includes_plans_but_does_not_create_transactions(client):
    response = client.post("/serenity-api/income-profiles", json={
        "name": "Salary", "income_type": "Salary", "pay_frequency": "Monthly",
        "annual_salary": "72000.00",
    })
    assert response.status_code == 201, response.text
    assert response.json()["calculated"]["gross_monthly"] == "6000.00"
    assert client.get("/serenity-api/accounts").json() == []
    backup = client.get("/serenity-api/export").json()
    assert backup["income_profiles"][0]["name"] == "Salary"
    assert backup["transactions"] == []


def test_income_api_preserves_take_home_and_calculates_net_summary(client):
    response = client.post("/serenity-api/income-profiles", json={
        "name": "Salary",
        "income_type": "Salary",
        "pay_frequency": "Semimonthly",
        "annual_salary": "78000.00",
        "expected_net_per_period": "2400.00",
    })
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["expected_net_per_period"] == "2400.00"
    assert body["calculated"]["net_monthly"] == "4800.00"
    assert body["calculated"]["net_annual"] == "57600.00"

    summary = client.get("/serenity-api/income-profiles/summary").json()
    assert summary["net_profile_count"] == 1
    assert summary["net_monthly"] == "4800.00"
    assert summary["net_annual"] == "57600.00"
    assert summary["net_is_partial"] is False


def test_income_api_hides_another_users_profile(real_auth_client):
    client = real_auth_client
    from auth import AUTH_COOKIE, issue_session

    client.cookies.set(AUTH_COOKIE, issue_session("owner-a", "fixture-owner-a"))
    created = client.post("/serenity-api/income-profiles", json={
        "name": "A job", "income_type": "Salary", "pay_frequency": "Annual",
        "annual_salary": "50000",
    }).json()
    client.cookies.set(AUTH_COOKIE, issue_session("owner-b", "fixture-owner-b"))
    assert client.get(f"/serenity-api/income-profiles/{created['id']}").status_code == 404
    assert client.get("/serenity-api/income-profiles").json() == []