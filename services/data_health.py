"""Read-only, owner-scoped input evidence, not a financial audit or write guard."""

from datetime import datetime, timedelta, timezone

from sqlalchemy.exc import SQLAlchemyError

from schemas.account import AccountCreate
from schemas.finance import BillCreate, DebtCreate, InvestmentCreate
from schemas.income_profile import IncomeProfileCreate
from schemas.reconciliation import SourceMapping
from schemas.transaction import TransactionCreate
from services import (
    account_service, finance_service, income_profile_service,
    portfolio_service, transaction_service,
)
from services.ownership import require_owner_id
from services import verification

# A disclosed review reminder, not a quote-age guarantee or accuracy judgement.
REVIEW_INTERVAL = timedelta(days=30)
DOMAINS = (
    ("accounts", "Account inputs", "ACTUAL", "/accounts"),
    ("bills", "Bill schedules", "PLANNED", "/finances"),
    ("debts", "Debt snapshots", "ACTUAL", "/finances"),
    ("investments", "Investment valuations", "MIXED", "/finances"),
    ("income", "Income plans", "PLANNED", "/income"),
)


def finding(code, status, message):
    return {"code": code, "status": status, "message": message}


def reading(domain, status, findings, size=None):
    key, label, basis, source = domain
    return {
        "key": key, "label": label, "basis": basis, "source": source,
        "status": status, "record_count": size, "findings": findings,
    }


def unknown_reading(domain, *, inconsistent=False):
    status = "INCONSISTENT" if inconsistent else "UNAVAILABLE"
    return reading(domain, status, [finding(
        "invalid_inputs" if inconsistent else "unavailable_inputs", status,
        "Stored inputs failed the domain's validation or relationship checks. "
        "The affected reading is unknown, not zero. Review the source records."
        if inconsistent else
        "These inputs could not be read reliably. Unknown does not mean empty, "
        "zero, or lost records. Other readings do not establish this one.",
    )])


def _validate(rows, converter, schema):
    for row in rows:
        if type(row.active) is not bool:
            raise ValueError("Invalid lifecycle")
        value = converter(row)
        schema.model_validate(value.model_dump())


def _freshness(rows, now):
    findings = []
    dates = []
    for row in rows:
        value = row.updated_at
        if value is None:
            findings.append(finding(
                "unknown_review_date", "UNKNOWN",
                "A last-edit timestamp is missing. Input freshness is unknown.",
            ))
            continue
        # SQLite's naive persisted timestamps represent UTC.
        value = value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value
        if value > now:
            raise ValueError("Future edit timestamp")
        dates.append(value)
    if any(value <= now - REVIEW_INTERVAL for value in dates):
        findings.append(finding(
            "review_due", "STALE",
            "At least one active input was last edited 30 or more days ago (UTC). "
            "This is a manual review reminder, not proof its amount is wrong. "
            "Editing notes is not verification of a balance, price, or income.",
        ))
    return findings


def _opening_freshness(openings, now):
    findings = []
    for opening in openings:
        # Immutable capture time is not a quote date. Use dated owner evidence.
        SourceMapping(
            source_id=opening.source_investment_id,
            valuation_as_of=opening.valuation_as_of_date,
            valuation_evidence=opening.valuation_evidence,
        )
        as_of = opening.valuation_as_of_date
        if as_of is None:
            if not any(f["code"] == "unknown_valuation_date" for f in findings):
                findings.append(finding(
                    "unknown_valuation_date", "UNKNOWN",
                    "A selected opening has no valuation as-of date. Its capture "
                    "time and retained source edit time do not establish price freshness.",
                ))
        elif as_of > now.date():
            raise ValueError("Future valuation date")
        elif (now.date() - as_of).days >= REVIEW_INTERVAL.days:
            if not any(f["code"] == "valuation_review_due" for f in findings):
                findings.append(finding(
                    "valuation_review_due", "STALE",
                    "A selected opening's owner-evidenced valuation date is 30 or "
                    "more days old (UTC). Review the manual value; it is not a live quote.",
                ))
    return findings


def _load(db, owner_id, key):
    if key == "accounts":
        rows = account_service.list_accounts(db, owner_id)
        _validate(rows, lambda r: account_service.to_account_read(r, db), AccountCreate)
        account_ids = {r.id for r in rows}
        for transaction in transaction_service.list_workspace_transactions(db, owner_id):
            if transaction.account_id not in account_ids:
                raise ValueError("Missing owner-scoped account")
            TransactionCreate.model_validate(
                transaction_service.to_transaction_read(transaction).model_dump()
            )
        return rows
    if key == "bills":
        rows = finance_service.list_bills(db, owner_id)
        _validate(rows, finance_service.to_bill_read, BillCreate)
        return rows
    if key == "debts":
        rows = finance_service.list_debts(db, owner_id)
        _validate(rows, finance_service.to_debt_read, DebtCreate)
        return rows
    if key == "investments":
        rows = finance_service.list_investments(db, owner_id)
        _validate(rows, finance_service.to_investment_read, InvestmentCreate)
        for row in rows:
            if row.portfolio_id is not None:
                portfolio_service.get_portfolio(db, owner_id, row.portfolio_id)
            if row.investment_account_id is not None:
                portfolio_service.get_investment_account(db, owner_id, row.investment_account_id)
        # Reuse canonical selection: retained converted sources are not current
        # valuations, and review-pending candidates do not count as assets.
        replaced, openings = portfolio_service.selected_valuation_records(db, owner_id)
        active_replaced = {r.id for r in rows if r.active and r.id in replaced}
        if active_replaced != {r.source_investment_id for r in openings}:
            raise ValueError("Missing selected valuation")
        for opening in openings:
            if (opening.original_entered_value_cents is None
                    or opening.original_entered_value_cents < 0
                    or opening.quantity_units is None or opening.quantity_units < 0
                    or opening.basis_status not in {"known", "unknown", "unverified"}
                    or (opening.basis_status == "known" and (
                        opening.entered_basis_cents is None or opening.entered_basis_cents < 0
                    ))):
                raise ValueError("Invalid selected valuation")
        return rows
    rows = income_profile_service.list_income_profiles(db, owner_id)
    _validate(rows, income_profile_service.to_income_profile_read, IncomeProfileCreate)
    return rows


def _verification_findings(db, owner_id, key, rows, now):
    targets = verification.domain_targets(db, owner_id, key, rows)
    saved = {(r.kind, r.target_id): r for r in verification.saved_rows(db, owner_id)}
    statuses = [
        verification.evidence_status(
            saved.get((t["kind"], t["target_id"])), t["snapshot"], now,
        ) for t in targets
    ]
    findings = []
    if "UNKNOWN" in statuses:
        findings.append(finding(
            "verification_unknown", "UNKNOWN",
            "At least one current balance or valuation has never been explicitly "
            "checked with dated owner evidence. Last edits are not verification.",
        ))
    if "CHANGED" in statuses:
        findings.append(finding(
            "verification_changed", "UNKNOWN",
            "At least one financial snapshot differs from its saved owner check. "
            "That evidence does not verify the current fact. Check it again.",
        ))
    if "STALE" in statuses:
        findings.append(finding(
            "verification_review_due", "STALE",
            "At least one matching owner's check is 30 or more days old (UTC). "
            "Review the manual fact; this is not external verification.",
        ))
    if "VERIFIED" in statuses:
        findings.append(finding(
            "owner_verified", "MANUAL",
            "At least one current snapshot matches explicit dated owner evidence. "
            "This is an owner assertion, not a bank, broker or live-feed certification.",
        ))
    checked = {
        (t["kind"], t["target_id"]) for t, status in zip(targets, statuses)
        if status in {"VERIFIED", "STALE"}
    }
    return findings, checked


def _observe(db, owner_id, domain, now):
    key = domain[0]
    rows = _load(db, owner_id, key)
    if not rows:
        return reading(domain, "MISSING", [finding(
            "no_records", "MISSING",
            "No records are stored for this workspace in this source. "
            "A summary's zero contribution is not confirmation of a real-world "
            "zero balance, no obligations, or no income.",
        )], 0)
    active = [r for r in rows if r.active]
    findings = [finding(
        "manual_inputs", "MANUAL",
        "These are manually entered inputs, not verified bank, broker, or live-feed evidence.",
    )]
    if not active:
        findings.append(finding(
            "no_active_inputs", "PARTIAL",
            "Only inactive records exist. Their exclusion from summaries does "
            "not confirm there are no real-world balances or obligations.",
        ))
    if key == "accounts":
        if active and not any(
            transaction_service.list_transactions(db, r.id, owner_id) for r in active
        ):
            findings.append(finding(
                "opening_only", "PARTIAL",
                "Active accounts have no recorded transactions. Current balances "
                "use entered opening balances and any reconciliation corrections; "
                "missing transaction history is not proof no money moved.",
            ))
    if key == "bills":
        findings.append(finding(
            "scheduled_not_paid", "MANUAL",
            "Recurring bill totals normalize schedules, not actual expenses or "
            "payment confirmations. One-time bills are excluded from recurring totals.",
        ))
        if any(r.due_date < now.date() for r in active):
            findings.append(finding(
                "past_due_schedule", "STALE",
                "An active bill's scheduled due date is before today (UTC). "
                "Review its schedule; this does not prove a missed payment.",
            ))
    if key == "debts":
        findings.append(finding(
            "entered_balance", "MANUAL",
            "Debt totals use entered active balances, not a lender statement or "
            "a payment-derived balance. A recorded zero is an input, not verification.",
        ))
    if key == "investments":
        selected = portfolio_service.eligible_legacy_investments(db, owner_id, rows)
        _, openings = portfolio_service.selected_valuation_records(db, owner_id)
        if any(r.review_pending for r in active):
            findings.append(finding(
                "pending_review", "PARTIAL",
                "Active review-pending candidates are excluded from net worth. "
                "Portfolio assignment is not account-balance reconciliation.",
            ))
        findings.append(finding(
            "selected_valuations", "MANUAL",
            "Only eligible legacy values or selected opening values contribute, "
            "never both representations. These are manual starting snapshots; "
            "reference instruments and hypothetical calculations are not actual trades.",
        ))
        if any(r.basis_status != "known" for r in openings):
            findings.append(finding(
                "unknown_cost_basis", "PARTIAL",
                "A selected opening has unknown or unverified cost basis. Its "
                "entered value does not establish cost basis or realized profit.",
            ))
        # Immutable opening snapshots have no last-edit field. Their capture
        # time cannot replace the owner-evidenced valuation date.
        opening_findings = _opening_freshness(openings, now)
        active = selected
    if key == "income":
        summary = income_profile_service.summarize(active)
        findings.append(finding(
            "planned_not_received", "MANUAL",
            "Income profiles calculate expected income, not received money. "
            "Actual receipts are account transactions; no forecast is posted.",
        ))
        if summary.variable_count:
            findings.append(finding(
                "variable_not_projected", "PARTIAL",
                "Variable income is not projected. Unknown projections are not zero income.",
            ))
        if summary.projected_count > summary.net_profile_count:
            findings.append(finding(
                "missing_take_home", "PARTIAL",
                "At least one projected profile has no expected take-home input. "
                "Take-home is unknown or partial, never a complete net-income total.",
            ))
    if key != "bills":
        edit_findings = _freshness(active, now)
        if key in {"accounts", "debts", "investments"}:
            verified_findings, checked = _verification_findings(db, owner_id, key, rows, now)
            findings.extend(verified_findings)
            # Still validate edit dates, but a matching explicit check supersedes
            # edit-age reminders. Financial rows and their timestamps stay intact.
            kind = {
                "accounts": "account_balance", "debts": "debt_balance",
                "investments": "legacy_valuation",
            }[key]
            edit_findings = _freshness(
                [r for r in active if (kind, r.id) not in checked], now,
            )
            if key == "investments":
                # Conversion valuation evidence remains independently validated.
                # A check can supersede its age/missing reminder, never corruption.
                opening_findings = _opening_freshness(
                    [r for r in openings if ("opening_valuation", r.id) not in checked], now,
                )
                findings.extend(opening_findings)
        findings.extend(edit_findings)
    priority = ("PARTIAL", "STALE", "UNKNOWN")
    status = next((s for s in priority if any(f["status"] == s for f in findings)), "MANUAL")
    # UNKNOWN findings map to partial input coverage, not a made-up status.
    return reading(domain, "PARTIAL" if status == "UNKNOWN" else status, findings, len(rows))


def data_health(db, owner_id, *, readable=True, now=None):
    """Only a verified workspace supplied by the API may choose the owner."""
    owner_id = require_owner_id(owner_id)
    now = now or datetime.now(timezone.utc)
    readings = []
    for domain in DOMAINS:
        if not readable:
            readings.append(unknown_reading(domain))
            continue
        try:
            # A failed SELECT must not poison other readings on PostgreSQL.
            with db.begin_nested():
                result = _observe(db, owner_id, domain, now)
            readings.append(result)
        except SQLAlchemyError:
            readings.append(unknown_reading(domain))
        except (ValueError, TypeError, ArithmeticError, KeyError, AttributeError):
            readings.append(unknown_reading(domain, inconsistent=True))
        except Exception:
            # Never return raw exception/SQL text or synthetic empty records.
            readings.append(unknown_reading(domain))
    return {
        "checked_at": now.isoformat(),
        "message": "Owner-scoped input evidence only, not a completeness certification "
        "or health score. Actual entries and planned amounts are distinct. "
        "Source links open the existing records for review. No write rules are changed.",
        "readings": readings,
    }