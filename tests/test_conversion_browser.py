"""Browser coverage for explicit owner conversion confirmations.

The page uses isolated in-memory test data. The approval/execution/reversal
workflow test stubs conversion writes at the browser boundary; only the real
version-2 execution preview and freshness verification are requested from the
test application. A separate test exercises the real fail-closed backup gate.
"""

import base64
import hashlib
import json
from datetime import datetime, timedelta

from playwright.sync_api import expect

from models.conversion import ReconciliationApproval


BASE = "http://serenity.test/portfolios"
API = "/serenity-api"


def create(client, path, payload):
    response = client.post(f"{API}/{path}", json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def setup_conversion_records(client):
    portfolio = create(client, "portfolios", {"name": "Disposable conversion review"})
    account = create(client, "accounts", {
        "name": "Synthetic brokerage", "account_type": "Brokerage",
        "classification": "Investment", "opening_balance": "10000.00",
    })
    container = create(client, "investment-accounts", {
        "name": "Synthetic investment sleeve", "portfolio_id": portfolio["id"],
        "account_id": account["id"],
    })
    instrument = create(client, "instruments", {
        "symbol": "SYN", "name": "Synthetic stock", "asset_type": "STOCK",
        "currency": "USD", "exchange": "NYSE", "tick_size": "0.01", "point_value": "1",
    })
    source = create(client, "investments", {
        "name": "Synthetic original shares", "ticker": "SYN", "quantity": "40",
        "cost_basis": "6000.00", "current_value": "8000.00",
    })
    return account, container, instrument, source


def start_execution_preview(page, account, container, instrument, source):
    page.goto(BASE)
    page.get_by_role("button", name="Review existing investments").click()
    expect(page.locator("#reconciliation-form")).to_be_visible()

    source_form = page.locator(f'#reconciliation-sources [data-source-id="{source["id"]}"]')
    source_form.locator('[name="investment_account_id"]').select_option(str(container["id"]))
    source_form.locator('[name="instrument_id"]').select_option(str(instrument["id"]))
    source_form.locator('[name="specification_id"]').select_option(str(instrument["specification_id"]))
    source_form.locator('[name="identity_confirmed"]').check()
    source_form.locator('[name="beneficial_ownership"]').select_option("personal")

    account_form = page.locator(f'#reconciliation-accounts [data-account-id="{account["id"]}"]')
    account_form.locator('[name="balance_meaning"]').select_option("combined")
    account_form.locator('[name="evidence"]').fill("Disposable synthetic statement")
    account_form.locator('[name="cash_cents"]').fill("200000")
    account_form.locator(f'[name="source_id"][value="{source["id"]}"]').check()
    account_form.locator('[name="complete"]').check()

    page.get_by_role("button", name="Create execution-capable preview").click()
    expect(page.locator("#reconciliation-report")).to_be_visible()
    expect(page.locator("#reconciliation-captured")).to_contain_text("report format 2")
    expect(page.locator("#conversion-readiness")).to_contain_text("Execution-capable report digest")
    expect(page.locator("#conversion-approval")).to_be_visible()
    return page.evaluate("reconciliationReportData"), page.evaluate("reconciliationToken")


def set_approval_metadata(page):
    now = datetime.now()
    page.locator("#conversion-backup-reference").fill("synthetic://browser-test-only")
    page.locator("#conversion-backup-cutoff").fill(
        (now - timedelta(minutes=5)).strftime("%Y-%m-%dT%H:%M")
    )
    page.locator("#conversion-rollback-deadline").fill(
        (now + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M")
    )


def test_browser_conversion_approval_execution_reversal_are_separate(page, client):
    account, container, instrument, source = setup_conversion_records(client)
    report, token = start_execution_preview(page, account, container, instrument, source)
    assert report["format_version"] == 2 and report["executable"] is True

    approval_requests = []
    execute_requests = []
    reverse_requests = []
    state = {"value": "approved"}
    approval_id = 741
    report_sha256 = hashlib.sha256(
        base64.urlsafe_b64decode(token.split(".", 1)[0] + "=" * (-len(token.split(".", 1)[0]) % 4))
    ).hexdigest()

    def evidence_body():
        events = []
        if state["value"] in ("executed", "reversed"):
            events.append({
                "event_id": 901, "approval_id": approval_id, "event_kind": "executed",
                "before_totals": report["current"], "after_totals": report["proposed"],
                "linked_ids": {"source_ids": [source["id"]], "opening_position_ids": [12]},
            })
        if state["value"] == "reversed":
            events.append({
                "event_id": 902, "approval_id": approval_id, "event_kind": "reversed",
                "before_totals": report["proposed"], "after_totals": report["current"],
                "linked_ids": {"opening_position_ids": [12]}, "reason": "Synthetic UI reversal",
            })
        return {
            "approval": {
                "id": approval_id, "state": state["value"], "report_sha256": report_sha256,
                "report_format_version": 2, "algorithm_version": report["algorithm_version"],
                "approved_at": "2025-01-01T00:00:00Z", "executed_at": (
                    "2025-01-01T00:01:00Z" if state["value"] in ("executed", "reversed") else None
                ), "reversed_at": "2025-01-01T00:02:00Z" if state["value"] == "reversed" else None,
                "rollback_deadline": "2099-01-01T00:00:00Z",
                "backup_evidence_reference": "synthetic://browser-test-only", "warnings": [],
            },
            "report": report,
            "opening_positions": ([{
                "id": 12, "source_investment_id": source["id"],
                "source_snapshot": report["sources"][0]["source"],
                "quantity_units": 4000000000, "original_entered_value_cents": 800000,
                "basis_status": "unverified", "status": "reversed" if state["value"] == "reversed" else "active",
            }] if state["value"] in ("executed", "reversed") else []),
            "eligibility": [], "cash_entries": [], "events": events,
        }

    def conversion_route(route):
        path = route.request.url.split("serenity-api/conversions", 1)[-1]
        if path == "/approvals":
            payload = route.request.post_data_json
            approval_requests.append(payload)
            route.fulfill(status=201, content_type="application/json", body=json.dumps({
                "approval_id": approval_id, "report_sha256": report_sha256, "state": "approved",
            }))
        elif path == f"/{approval_id}":
            route.fulfill(status=200, content_type="application/json", body=json.dumps(evidence_body()))
        elif path == f"/{approval_id}/execute":
            payload = route.request.post_data_json
            execute_requests.append(payload)
            state["value"] = "executed"
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "event_id": 901, "approval_id": approval_id, "event_kind": "executed",
                "before_totals": report["current"], "after_totals": report["proposed"],
                "linked_ids": {"source_ids": [source["id"]], "opening_position_ids": [12]},
            }))
        elif path == f"/{approval_id}/reverse":
            payload = route.request.post_data_json
            reverse_requests.append(payload)
            state["value"] = "reversed"
            route.fulfill(status=200, content_type="application/json", body=json.dumps({
                "event_id": 902, "approval_id": approval_id, "event_kind": "reversed",
                "before_totals": report["proposed"], "after_totals": report["current"],
                "linked_ids": {"opening_position_ids": [12]},
            }))
        else:
            route.fulfill(status=404, content_type="application/json", body='{"detail":"Not found"}')

    page.route("**/serenity-api/conversions/**", conversion_route)

    # Cancel is a no-op and clears every per-record/account confirmation.
    page.locator('#conversion-record-confirmations [name="approved_source_id"]').check()
    page.locator('#conversion-record-confirmations [name="approved_account_id"]').check()
    page.locator("#conversion-approval-confirm").check()
    page.get_by_role("button", name="Cancel / no-op").click()
    expect(page.locator('#conversion-record-confirmations input[type="checkbox"]:checked')).to_have_count(0)
    assert approval_requests == []

    page.locator('#conversion-record-confirmations [name="approved_source_id"]').check()
    page.locator('#conversion-record-confirmations [name="approved_account_id"]').check()
    set_approval_metadata(page)
    page.locator("#conversion-approval-confirm").check()
    page.get_by_role("button", name="Store owner approval only").click()
    expect(page.locator("#conversion-approval-message")).to_contain_text("No conversion was executed")
    expect(page.locator("#conversion-execution")).to_be_visible()
    assert len(approval_requests) == 1
    approval_payload = approval_requests[0]
    assert approval_payload["report_token"] == token
    assert approval_payload["report_sha256"] == report_sha256
    assert approval_payload["selected_source_ids"] == [source["id"]]
    assert approval_payload["account_corrections_cents"] == {
        str(account["id"]): -800000,
    }
    assert approval_payload["confirm_approval"] is True
    assert "backup_cutoff" in approval_payload
    # Normal UI has no test-only/synthetic bypass control or request flag.
    assert "test_only_synthetic" not in approval_payload
    expect(page.locator("#conversion-approval input[name='test_only_synthetic']")).to_have_count(0)

    page.locator("#conversion-execution-id").fill(str(approval_id))
    page.get_by_role("button", name="Execute approved conversion").click()
    expect(page.locator("#conversion-execution-message")).to_contain_text("separate confirmation checkbox")
    assert execute_requests == []

    page.locator("#conversion-execution-confirm").check()
    page.locator("#conversion-execution-id").fill("not-the-approval-id")
    page.get_by_role("button", name="Execute approved conversion").click()
    expect(page.locator("#conversion-execution-message")).to_contain_text("exact approval ID")
    assert execute_requests == []

    page.locator("#conversion-execution-id").fill(str(approval_id))
    page.get_by_role("button", name="Execute approved conversion").click()
    expect(page.locator("#conversion-evidence-details")).to_contain_text("executed")
    assert len(execute_requests) == 1
    assert execute_requests[0]["confirm_execute"] is True
    assert len(execute_requests[0]["idempotency_key"]) >= 8

    page.on("dialog", lambda dialog: dialog.accept())
    page.locator("#conversion-reversal-reason").fill("Synthetic UI reversal")
    page.locator("#conversion-reversal-confirm").check()
    page.get_by_role("button", name="Request safe reversal").click()
    expect(page.locator("#conversion-evidence-details")).to_contain_text("reversed")
    assert len(reverse_requests) == 1
    assert reverse_requests[0] == {
        "confirm_reverse": True, "reason": "Synthetic UI reversal",
    }


def test_browser_normal_approval_fails_closed_without_real_backup_gate(page, client, db):
    account, container, instrument, source = setup_conversion_records(client)
    start_execution_preview(page, account, container, instrument, source)
    page.locator('#conversion-record-confirmations [name="approved_source_id"]').check()
    page.locator('#conversion-record-confirmations [name="approved_account_id"]').check()
    set_approval_metadata(page)
    page.locator("#conversion-approval-confirm").check()
    approval_posts = []
    page.on("request", lambda request: approval_posts.append(request.post_data_json)
            if request.method == "POST" and request.url.endswith("/serenity-api/conversions/approvals")
            else None)

    page.get_by_role("button", name="Store owner approval only").click()
    expect(page.locator("#conversion-approval-message")).to_contain_text(
        "Verified off-host backup evidence is required"
    )
    assert len(approval_posts) == 1
    assert "test_only_synthetic" not in approval_posts[0]
    assert db.query(ReconciliationApproval).count() == 0
