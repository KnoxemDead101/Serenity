"""Browser coverage for Phase 1 instrument administration and server-side estimates."""

import pytest
from playwright.sync_api import expect


BASE_URL = "http://serenity.test/profit-engine"
INSTRUMENT_URL = "/serenity-api/instruments"


def test_instrument_versions_and_archive_from_browser(page, client):
    page.goto(BASE_URL)
    expect(page.get_by_role("heading", name="Profit Engine")).to_be_visible()
    expect(page.locator("#instruments-body")).to_contain_text("No instruments yet.")
    form = page.locator("#instrument-form")
    form.locator("[name=symbol]").fill("VTI")
    form.locator("[name=name]").fill("Total market ETF")
    form.locator("[name=asset_type]").select_option("ETF")
    form.get_by_role("button", name="Add instrument").click()
    expect(page.locator("#instrument-message")).to_have_text("Instrument VTI added.")
    row = page.locator("#instruments-body tr").filter(has_text="VTI")
    expect(row).to_contain_text("v1")
    record = client.get(INSTRUMENT_URL).json()[0]
    first_spec = record["specification_id"]
    row.get_by_role("button", name="Edit").click()
    expect(form.locator("[name=symbol]")).to_be_disabled()
    form.locator("[name=name]").fill("Updated market ETF")
    form.get_by_role("button", name="Save new version").click()
    expect(page.locator("#instrument-message")).to_contain_text("New specification version saved")
    expect(row).to_contain_text("v2")
    updated = client.get(f"{INSTRUMENT_URL}/{record['id']}").json()
    assert updated["specification_id"] != first_spec
    row.get_by_role("button", name="Versions").click()
    expect(page.locator("#versions-body tr")).to_have_count(2)
    expect(page.locator("#versions-body")).to_contain_text("Total market ETF")
    expect(page.locator("#versions-body")).to_contain_text("Updated market ETF")

    requests = []
    page.on("request", lambda request: requests.append(request)
            if request.method == "POST" and request.url.endswith("/deactivate") else None)
    page.once("dialog", lambda dialog: dialog.dismiss())
    row.get_by_role("button", name="Archive").click()
    assert not requests
    assert client.get(f"{INSTRUMENT_URL}/{record['id']}").json()["active"] is True
    page.once("dialog", lambda dialog: dialog.accept())
    row.get_by_role("button", name="Archive").click()
    expect(row.get_by_text("Archived")).to_be_visible()
    expect(page.locator("#calculator-form [name=specification_id] option")).to_have_count(1)
    assert client.get(f"{INSTRUMENT_URL}/{record['id']}").json()["active"] is False
    row.get_by_role("button", name="Reactivate").click()
    expect(row.get_by_role("button", name="Archive")).to_be_visible()
    expect(page.locator("#calculator-form [name=specification_id] option")).to_have_count(2)
    assert client.get(f"{INSTRUMENT_URL}/{record['id']}/specifications").json()[0]["specification_id"] == first_spec


@pytest.mark.parametrize(
    "instrument,quantity,entry,exit_price,stop,target,expected_net,expected_risk",
    [
        (
            {"symbol": "MINI", "name": "Mini contract", "asset_type": "FUTURE",
             "tick_size": "0.25", "point_value": "50"},
            "2", "5000", "5002", "4998", "5004", "$200.00", "$200.00",
        ),
        (
            {"symbol": "MICRO", "name": "Micro contract", "asset_type": "FUTURE",
             "tick_size": "0.25", "point_value": "5"},
            "2", "5000", "5002", "4998", "5004", "$20.00", "$20.00",
        ),
        (
            {"symbol": "FRACTION", "name": "Fractional share", "asset_type": "STOCK",
             "tick_size": "0.01", "point_value": "1"},
            "0.147392", "10", "11", "9", "12", "$0.15", "$0.15",
        ),
    ],
)
def test_calculator_displays_python_results(
    page, client, instrument, quantity, entry, exit_price, stop, target,
    expected_net, expected_risk,
):
    created = client.post(INSTRUMENT_URL, json=instrument)
    assert created.status_code == 201, created.text
    spec = created.json()
    summary_before = client.get("/serenity-api/dashboard/summary").json()
    page.goto(BASE_URL)
    form = page.locator("#calculator-form")
    expect(form.locator("[name=specification_id] option")).to_have_count(2)
    form.locator("[name=specification_id]").select_option(str(spec["specification_id"]))
    form.locator("[name=quantity]").fill(quantity)
    form.locator("[name=entry_price]").fill(entry)
    form.locator("[name=exit_price]").fill(exit_price)
    form.locator("[name=stop_price]").fill(stop)
    form.locator("[name=target_price]").fill(target)
    form.get_by_role("button", name="Calculate").click()
    expect(page.locator("#calculator-results")).to_be_visible()
    expect(page.locator("#result-net_pnl")).to_have_text(expected_net)
    expect(page.locator("#result-risk")).to_contain_text(expected_risk)
    expect(page.locator("#result-planned_rr")).to_contain_text("2.00000000")
    assert client.get("/serenity-api/investments").json() == []
    assert client.get("/serenity-api/dashboard/summary").json() == summary_before


def test_invalid_calculation_keeps_inputs_and_does_not_show_old_result(page, client):
    created = client.post(INSTRUMENT_URL, json={
        "symbol": "TEST", "name": "Test contract", "asset_type": "FUTURE",
        "tick_size": "0.25", "point_value": "50",
    })
    assert created.status_code == 201, created.text
    page.goto(BASE_URL)
    form = page.locator("#calculator-form")
    form.locator("[name=specification_id]").select_option(
        str(created.json()["specification_id"])
    )
    form.locator("[name=quantity]").fill("1")
    form.locator("[name=entry_price]").fill("5000")
    form.locator("[name=exit_price]").fill("5002")
    form.get_by_role("button", name="Calculate").click()
    expect(page.locator("#calculator-results")).to_be_visible()
    form.locator("[name=entry_price]").fill("5000.01")  # invalid futures tick
    form.get_by_role("button", name="Calculate").click()
    expect(page.locator("#calculator-message")).to_be_visible()
    expect(page.locator("#calculator-results")).to_be_hidden()
    expect(form.locator("[name=entry_price]")).to_have_value("5000.01")


def test_failed_instrument_save_preserves_edit_draft(page, client):
    created = client.post(INSTRUMENT_URL, json={
        "symbol": "EDIT", "name": "Original instrument", "asset_type": "ETF",
    })
    assert created.status_code == 201, created.text
    page.goto(BASE_URL)
    row = page.locator("#instruments-body tr").filter(has_text="EDIT")
    row.get_by_role("button", name="Edit").click()
    form = page.locator("#instrument-form")
    form.locator("[name=name]").fill("Work in progress")
    page.route(f"**{INSTRUMENT_URL}/{created.json()['id']}", lambda route: route.fulfill(
        status=503, content_type="application/json",
        body='{"detail":"Saving is unavailable; try again"}'
    ) if route.request.method == "PUT" else route.continue_())
    form.get_by_role("button", name="Save new version").click()
    expect(page.locator("#instrument-message")).to_have_text("Saving is unavailable; try again")
    expect(form.locator("[name=name]")).to_have_value("Work in progress")
    expect(row).to_contain_text("v1")
    assert client.get(f"{INSTRUMENT_URL}/{created.json()['id']}").json()["version"] == 1