"""Smoke-test the Income Profiles screen in Chromium."""

import pytest

expect = pytest.importorskip("playwright.sync_api").expect


def test_income_profile_can_be_created_and_projected_in_browser(page):
    page.goto("http://serenity.test/income")
    page.locator("[name=name]").fill("Warehouse job")
    page.locator("[name=hourly_rate]").fill("20.00")
    page.locator("[name=expected_hours_per_week]").fill("40")
    page.locator("[name=standard_hours_per_week]").fill("40")
    page.get_by_role("button", name="Add income profile").click()
    expect(page.locator("#incomes-body")).to_contain_text("Warehouse job")
    expect(page.locator("#gross-monthly")).to_have_text("$3,466.67")
    expect(page.locator("#gross-annual")).to_have_text("$41,600.00")