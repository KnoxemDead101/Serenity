"""Isolated browser checks for a read-only, owner-private reconciliation draft."""

from playwright.sync_api import expect


BASE = "http://serenity.test/portfolios"
API = "/serenity-api"


def create(client, path, payload):
    response = client.post(f"{API}/{path}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def setup_records(client):
    portfolio = create(client, "portfolios", {"name": "Private review"})
    clean = create(client, "accounts", {
        "name": "Cash only brokerage", "account_type": "Brokerage",
        "classification": "Investment", "opening_balance": "75.00",
    })
    overlap = create(client, "accounts", {
        "name": "Combined brokerage", "account_type": "Brokerage",
        "classification": "Investment", "opening_balance": "325.00",
    })
    containers = [
        create(client, "investment-accounts", {
            "name": name, "portfolio_id": portfolio["id"], "account_id": account["id"],
        })
        for name, account in [("Cash container", clean), ("Combined container", overlap)]
    ]
    instrument = create(client, "instruments", {
        "symbol": "ABC", "name": "Example stock", "asset_type": "STOCK",
        "currency": "USD", "exchange": "NYSE", "tick_size": "0.01", "point_value": "1",
    })
    sources = [
        create(client, "investments", {
            "name": "Clean stock", "ticker": "ABC", "quantity": "2",
            "cost_basis": "40.00", "current_value": "100.00",
        }),
        create(client, "investments", {
            "name": "Overlapping stock", "ticker": "ABC", "quantity": "4",
            "cost_basis": "0.00", "current_value": "200.00",
        }),
    ]
    return clean, overlap, containers, instrument, sources


def source_form(page, source):
    return page.locator(f'#reconciliation-sources [data-source-id="{source["id"]}"]')


def test_new_investment_selects_portfolio_and_opens_review_without_counting(page, client):
    portfolio = create(client, "portfolios", {"name": "Retirement"})
    account = create(client, "accounts", {
        "name": "Brokerage", "account_type": "Brokerage",
        "classification": "Personal", "opening_balance": "100.00",
    })
    container = create(client, "investment-accounts", {
        "name": "Brokerage sleeve", "portfolio_id": portfolio["id"], "account_id": account["id"],
    })
    before = client.get(f"{API}/dashboard/summary").json()
    page.goto("http://serenity.test/finances")
    form = page.locator("#investment-form")
    form.locator('[name="portfolio_id"]').select_option(str(portfolio["id"]))
    form.locator('[name="name"]').fill("New shares")
    form.locator('[name="ticker"]').fill("VTI")
    form.locator('[name="quantity"]').fill("1")
    form.locator('[name="cost_basis"]').fill("80")
    form.locator('[name="current_value"]').fill("100")
    form.get_by_role("button", name="Add investment").click()
    source = client.get(f"{API}/investments").json()[0]
    assert source["review_pending"] is True
    assert source["portfolio_id"] == portfolio["id"]
    assert source["investment_account_id"] is None
    assert client.get(f"{API}/dashboard/summary").json() == before
    expect(page).to_have_url(f"http://serenity.test/portfolios?review={source['id']}")
    selected = source_form(page, source)
    expect(selected).to_be_visible()
    expect(selected).to_contain_text("Retirement")
    selected.locator('[name="account_id"]').select_option(str(account["id"]))
    assert client.get(f"{API}/dashboard/summary").json() == before


def account_form(page, account):
    return page.locator(f'#reconciliation-accounts [data-account-id="{account["id"]}"]')


def begin(page):
    page.goto(BASE)
    page.get_by_role("button", name="Review existing investments").click()
    expect(page.locator("#reconciliation-form")).to_be_visible()


def map_source(page, source, container, instrument, zero=False):
    form = source_form(page, source)
    form.locator('[name="investment_account_id"]').select_option(str(container["id"]))
    form.locator('[name="instrument_id"]').select_option(str(instrument["id"]))
    form.locator('[name="specification_id"]').select_option(str(instrument["specification_id"]))
    form.locator('[name="identity_confirmed"]').check()
    form.locator('[name="beneficial_ownership"]').select_option("personal")
    if zero:
        form.locator('[name="zero_basis_reviewed"]').check()


def evidence(page, account, source, meaning, cash):
    form = account_form(page, account)
    form.locator('[name="balance_meaning"]').select_option(meaning)
    form.locator('[name="evidence"]').fill("Reviewed original ledger statement")
    form.locator('[name="cash_cents"]').fill(str(cash))
    form.locator(f'[name="source_id"][value="{source["id"]}"]').check()
    form.locator('[name="complete"]').check()


def test_clean_and_overlap_report_preserves_live_dashboard(page, client):
    clean, overlap, containers, instrument, sources = setup_records(client)
    before = client.get(f"{API}/dashboard/summary").json()
    begin(page)
    map_source(page, sources[0], containers[0], instrument)
    map_source(page, sources[1], containers[1], instrument, zero=True)
    evidence(page, clean, sources[0], "cash_only", 7500)
    evidence(page, overlap, sources[1], "combined", 12500)
    source_form(page, sources[0]).locator('[name="valuation_as_of"]').fill("2024-03-15")
    source_form(page, sources[0]).locator('[name="valuation_evidence"]').fill("Owner's dated record")
    page.get_by_role("button", name="Calculate read-only preview").click()
    expect(page.locator("#reconciliation-report")).to_be_visible()
    expect(page.locator("#reconciliation-outcomes")).to_contain_text("eligible")
    expect(page.locator("#reconciliation-outcomes")).to_contain_text("Owner's dated record")
    expect(page.locator("#reconciliation-totals")).to_contain_text("$300.00")
    expect(page.locator("#reconciliation-account-results")).to_contain_text("−$200.00")
    expect(page.locator("#reconciliation-delta")).to_contain_text("−$200.00")
    expect(page.locator("#reconciliation-explanations")).to_contain_text("duplicate-count")
    assert client.get(f"{API}/dashboard/summary").json() == before
    page.get_by_role("button", name="Check report freshness").click()
    expect(page.locator("#reconciliation-status")).to_contain_text("verified")
    with page.expect_download() as download:
        page.get_by_role("button", name="Export signed report JSON").click()
    assert download.value.suggested_filename == "serenity-reconciliation-signed.json"
    assert client.get(f"{API}/dashboard/summary").json() == before


def test_partial_unknown_inactive_cancel_and_stale_export(page, client):
    clean, overlap, containers, instrument, sources = setup_records(client)
    inactive = create(client, "investments", {
        "name": "Inactive original", "quantity": "1", "cost_basis": "1.00",
        "current_value": "5.00",
    })
    assert client.post(f'{API}/investments/{inactive["id"]}/deactivate').status_code == 200
    before = client.get(f"{API}/dashboard/summary").json()
    begin(page)
    map_source(page, sources[0], containers[0], instrument)
    map_source(page, sources[1], containers[1], instrument)  # zero basis not reviewed
    evidence(page, clean, sources[0], "cash_only", 7500)
    # Account declaration is incomplete: no source ids / complete attestation.
    form = account_form(page, overlap)
    form.locator('[name="balance_meaning"]').select_option("unknown")
    page.get_by_role("button", name="Calculate read-only preview").click()
    expect(page.locator("#reconciliation-report")).to_be_visible()
    expect(page.locator("#reconciliation-outcomes")).to_contain_text("inactive")
    expect(page.locator("#reconciliation-outcomes")).to_contain_text("unresolved")
    expect(page.locator("#reconciliation-outcomes")).to_contain_text("zero basis")
    expect(page.locator("#reconciliation-account-results")).to_contain_text("no partial correction")
    assert client.get(f"{API}/dashboard/summary").json() == before
    page.get_by_role("button", name="Check report freshness").click()
    expect(page.locator("#reconciliation-status")).to_contain_text("verified")
    create(client, "investments", {
        "name": "Changed since capture", "quantity": "1", "cost_basis": "1.00",
        "current_value": "3.00",
    })
    page.get_by_role("button", name="Check report freshness").click()
    expect(page.locator("#reconciliation-status")).to_contain_text("Stale")
    page.get_by_role("button", name="Export signed report JSON").click()
    expect(page.locator("#reconciliation-status")).to_contain_text("Export refused")
    page.get_by_role("button", name="Cancel and discard preview").click()
    expect(page.locator("#reconciliation-form")).to_be_hidden()
    expect(page.locator("#reconciliation-report")).to_be_hidden()
    expect(page.locator("#reconciliation-sources")).to_be_empty()
    assert client.get(f"{API}/dashboard/summary").json()["investment_value"] == "303.00"


def test_session_expiration_discards_report_and_owner_draft(page, client):
    setup_records(client)
    begin(page)
    page.get_by_role("button", name="Calculate read-only preview").click()
    expect(page.locator("#reconciliation-report")).to_be_visible()
    page.route("**/serenity-api/reconciliation/verify", lambda route: route.fulfill(
        status=401, content_type="application/json", body='{"detail":"Session ended"}'
    ))
    page.get_by_role("button", name="Check report freshness").click()
    expect(page.get_by_role("heading", name="Your session has ended")).to_be_visible()
    expect(page.locator("#reconciliation-form")).to_have_count(0)
    expect(page.locator("#reconciliation-report")).to_have_count(0)
    expect(page.get_by_text("Clean stock")).to_have_count(0)
    assert page.evaluate("reconciliationToken") is None
    assert page.evaluate("reconciliationSources.length") == 0