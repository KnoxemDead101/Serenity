"""Owner-private shadow calculations. No writes, posting, or valuation switch.

One SQL statement captures every dependency so even READ COMMITTED PostgreSQL
and legacy sqlite3 transaction handling cannot mix cutoffs between tables.
Reports retain the exact source facts and user declarations, signed separately
from authentication cookies. They are evidence for review, not executable plans.
"""

import base64
import hashlib
import hmac
import json
from datetime import date, datetime

from sqlalchemy import Boolean, String, cast, func, literal, select, union_all
from sqlalchemy.orm import Session

from auth import _secret
from models.account import Account, utc_now
from models.conversion import (
    CashReconciliationEntry, ConversionEvent, OpeningPosition, ReconciliationApproval,
    ValuationEligibility,
)
from models.bill import Bill
from models.business import Business
from models.debt import Debt
from models.dependent import Dependent
from models.income_profile import IncomeProfile
from models.instrument import Instrument, InstrumentSpecification
from models.investment import Investment
from models.goal import Goal
from models.goal_composition import GoalItem, GoalMilestone, GoalCheckpoint
from models.portfolio import InvestmentAccount, Portfolio
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from schemas.reconciliation import PreviewRequest
from services.ownership import require_owner_id
from services.financial_write_lock import lock_owner_financial_writes


class ReconciliationNotFound(ValueError):
    pass


class StaleReport(ValueError):
    pass


DEPENDENCIES = (
    Account, Bill, Business, Debt, Dependent, IncomeProfile, Instrument,
    InstrumentSpecification, Investment, Portfolio, InvestmentAccount,
    Transaction, TransactionCorrection, Goal, GoalItem, GoalMilestone, GoalCheckpoint,
)


def _canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def capture_dependencies(db: Session, owner_id: str) -> dict:
    """Read all columns, including inactive/deleted rows, in one DB snapshot."""
    owner_id = require_owner_id(owner_id)
    json_function = func.json_build_object if db.get_bind().dialect.name == "postgresql" else func.json_object
    statements = []
    for model in DEPENDENCIES:
        table = model.__table__
        pairs = [part for column in table.columns for part in (literal(column.name), column)]
        statements.append(select(
            literal(table.name).label("table_name"),
            table.c.id.label("row_id"),
            cast(json_function(*pairs), String).label("row_json"),
        ).where(table.c.owner_id == owner_id))
    snapshot = {model.__tablename__: [] for model in DEPENDENCIES}
    with db.no_autoflush:
        rows = db.execute(union_all(*statements).order_by("table_name", "row_id")).all()
    models = {model.__tablename__: model for model in DEPENDENCIES}
    for table_name, _, encoded in rows:
        row = json.loads(encoded)
        for column in models[table_name].__table__.columns:
            if isinstance(column.type, Boolean) and row[column.name] is not None:
                row[column.name] = bool(row[column.name])
        # SQLite JSON columns embedded by json_object can arrive as JSON text.
        if table_name == "transaction_corrections":
            for key in ("before", "after"):
                if isinstance(row[key], str):
                    row[key] = json.loads(row[key])
        snapshot[table_name].append(row)
    return snapshot


def _fingerprint(snapshot: dict) -> str:
    return hashlib.sha256(_canonical(snapshot)).hexdigest()


def _require(index: dict, row_id: int) -> dict:
    if row_id not in index:
        raise ReconciliationNotFound("Reconciliation resource not found")
    return index[row_id]


def _unique(rows, key):
    index = {}
    for row in rows:
        value = getattr(row, key)
        if value in index:
            raise ValueError(f"Duplicate {key}")
        index[value] = row
    return index


def _sign(report: dict) -> str:
    payload = base64.urlsafe_b64encode(_canonical(report)).decode("ascii")
    version = report["format_version"]
    signature = hmac.new(
        _secret(), f"serenity-reconciliation-v{version}:".encode("ascii") + payload.encode("ascii"),
        hashlib.sha256,
    ).hexdigest()
    return payload + "." + signature


def _decode(token: str, owner_id: str) -> dict:
    secret = _secret()
    try:
        payload, signature = token.split(".")
        # Decode only the signed body first to select its versioned domain.
        unsigned = json.loads(base64.b64decode(payload, altchars=b"-_", validate=True))
        version = unsigned.get("format_version")
        if version not in (1, 2):
            raise ValueError("Unsupported report version")
        expected = hmac.new(
            secret, f"serenity-reconciliation-v{version}:".encode("ascii") + payload.encode("ascii"),
            hashlib.sha256,
        ).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        report = unsigned
        if report["owner_id"] != require_owner_id(owner_id):
            raise ValueError("Wrong report scope")
        return report
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ReconciliationNotFound("Reconciliation report not found") from exc


def _conversion_snapshot(db: Session, owner_id: str) -> dict:
    state = {}
    # Approval creation is not a financial mutation. Including its own signed
    # report here would stale every approved batch and recursively embed reports.
    for model in (OpeningPosition, ValuationEligibility, CashReconciliationEntry, ConversionEvent):
        rows = (db.query(model).filter(model.owner_id == owner_id)
                .populate_existing().order_by(model.id).all())
        state[model.__tablename__] = [
            {
                column.name: (
                    value.isoformat() if isinstance(value, (date, datetime))
                    else value.hex() if isinstance(value, bytes) else value
                )
                for column in model.__table__.columns
                for value in (getattr(row, column.name),)
            }
            for row in rows
        ]
    return state


def _execution_snapshot(db: Session, owner_id: str) -> dict:
    snapshot = capture_dependencies(db, owner_id)
    snapshot["conversion_state"] = _conversion_snapshot(db, owner_id)
    return snapshot


def account_conversion_history(state: dict, account_id: int) -> dict:
    """Exact prior account links, including reversed history, for fresh review."""
    positions = [
        row for row in state.get("opening_positions", [])
        if row["cash_account_id"] == account_id
    ]
    entries = [
        row for row in state.get("cash_reconciliation_entries", [])
        if row["account_id"] == account_id
    ]
    return {
        "source_ids": sorted(row["source_investment_id"] for row in positions),
        "opening_position_ids": sorted(row["id"] for row in positions),
        "cash_entry_ids": sorted(row["id"] for row in entries),
        "active_source_ids": sorted(
            row["source_investment_id"] for row in positions if row["status"] == "active"
        ),
        "previous_correction_cents": sum(row["delta_cents"] for row in entries),
    }


def validate_prior_account_evidence(evidence: dict, history: dict) -> None:
    """A checkbox alone cannot attest to an unspecified set of prior facts."""
    for evidence_key, history_key in (
        ("prior_opening_position_ids", "opening_position_ids"),
        ("prior_cash_entry_ids", "cash_entry_ids"),
    ):
        declared = evidence.get(evidence_key, [])
        if len(set(declared)) != len(declared) or set(declared) != set(history[history_key]):
            raise ValueError("Prior conversion references must enumerate the exact account history")
    if ((history["opening_position_ids"] or history["cash_entry_ids"])
            and evidence.get("prior_conversion_complete") is not True):
        raise ValueError("Prior conversions and corrected cash require explicit completeness attestation")


def build_preview(db: Session, owner_id: str, data: PreviewRequest, *, executable=False) -> dict:
    owner_id = require_owner_id(owner_id)
    captured_at = utc_now().isoformat()
    snapshot = _execution_snapshot(db, owner_id) if executable else capture_dependencies(db, owner_id)
    conversion_state = snapshot["conversion_state"] if executable else _conversion_snapshot(db, owner_id)
    conversion_state = conversion_state or {}
    conversion_positions = conversion_state.get("opening_positions", [])
    conversion_eligibility = conversion_state.get("valuation_eligibility", [])
    conversion_cash_entries = conversion_state.get("cash_reconciliation_entries", [])
    historical_source_ids = {
        row["source_investment_id"] for row in conversion_positions
    } | {
        row["source_investment_id"] for row in conversion_eligibility
    }
    active_replaced_source_ids = {
        row["source_investment_id"] for row in conversion_eligibility
        if row["status"] == "active" and row["representation"] == "opening"
    }
    selected_opening_ids = {
        row["opening_position_id"] for row in conversion_eligibility
        if row["status"] == "active" and row["representation"] == "opening"
    }
    active_investment_ids = {
        row["id"] for row in snapshot["investments"] if row["active"]
    }
    current_opening_values = {}
    if not executable:
        # Format 1 retains its historical, hypothetical legacy semantics.
        active_replaced_source_ids = set()
        selected_opening_ids = set()
    for position in conversion_positions:
        if (position["id"] in selected_opening_ids and position["status"] == "active"
                and position["source_investment_id"] in active_investment_ids):
            source_id = position["source_investment_id"]
            current_opening_values[source_id] = (
                current_opening_values.get(source_id, 0)
                + position["original_entered_value_cents"]
            )
    indexes = {
        name: {row["id"]: row for row in rows}
        for name, rows in snapshot.items() if isinstance(rows, list)
    }
    mappings = _unique(data.mappings, "source_id")
    evidence = _unique(data.accounts, "account_id")
    targets = {}
    # Validate every supplied identifier, including inactive/unresolved inputs.
    for mapping in data.mappings:
        source = _require(indexes["investments"], mapping.source_id)
        for field, table in (
            ("portfolio_id", "portfolios"),
            ("account_id", "accounts"),
            ("investment_account_id", "investment_accounts"),
            ("instrument_id", "instruments"),
            ("specification_id", "instrument_specifications"),
        ):
            value = getattr(mapping, field)
            if value is not None:
                _require(indexes[table], value)
        if mapping.specification_id is not None and mapping.instrument_id is not None:
            if indexes["instrument_specifications"][mapping.specification_id]["instrument_id"] != mapping.instrument_id:
                raise ReconciliationNotFound("Reconciliation resource not found")
        if source["portfolio_id"] is not None:
            if mapping.portfolio_id != source["portfolio_id"]:
                raise ReconciliationNotFound("Reconciliation resource not found")
            if not executable and mapping.investment_account_id is not None:
                raise ReconciliationNotFound("Reconciliation resource not found")
            if mapping.account_id is not None:
                targets[mapping.source_id] = mapping.account_id
        elif mapping.portfolio_id is not None or mapping.account_id is not None:
            raise ReconciliationNotFound("Reconciliation resource not found")
        if mapping.investment_account_id is not None:
            container = indexes["investment_accounts"][mapping.investment_account_id]
            if source["portfolio_id"] is not None:
                if (container["portfolio_id"] != source["portfolio_id"]
                        or container["account_id"] != mapping.account_id):
                    raise ReconciliationNotFound("Reconciliation resource not found")
            elif source["review_pending"] and source["investment_account_id"] != container["id"]:
                raise ReconciliationNotFound("Reconciliation resource not found")
            _require(indexes["accounts"], container["account_id"])
            _require(indexes["portfolios"], container["portfolio_id"])
            targets[mapping.source_id] = container["account_id"]
    declared = {}
    for item in data.accounts:
        _require(indexes["accounts"], item.account_id)
        if executable:
            for field, rows, account_key in (
                ("prior_opening_position_ids", conversion_positions, "cash_account_id"),
                ("prior_cash_entry_ids", conversion_cash_entries, "account_id"),
            ):
                for row_id in getattr(item, field):
                    row = _require({row["id"]: row for row in rows}, row_id)
                    if row[account_key] != item.account_id:
                        raise ReconciliationNotFound("Reconciliation resource not found")
        if len(set(item.source_ids)) != len(item.source_ids):
            raise ValueError("Duplicate source_ids in account evidence")
        for source_id in item.source_ids:
            _require(indexes["investments"], source_id)
            if source_id in declared:
                raise ValueError("A source cannot be declared for multiple accounts")
            declared[source_id] = item.account_id
            if source_id in targets and targets[source_id] != item.account_id:
                raise ReconciliationNotFound("Reconciliation resource not found")
            if executable and source_id in historical_source_ids:
                position = next(row for row in conversion_positions
                                if row["source_investment_id"] == source_id)
                if position["cash_account_id"] != item.account_id:
                    raise ReconciliationNotFound("Reconciliation resource not found")

    sources = []
    for source in snapshot["investments"]:
        mapping = mappings.get(source["id"])
        warnings = []
        if source["review_pending"] and (mapping is None or (
            mapping.portfolio_id != source["portfolio_id"] if source["portfolio_id"] is not None
            else mapping.investment_account_id != source["investment_account_id"]
        )):
            warnings.append("Pending investment must be reviewed for its assigned portfolio.")
        source_had_conversion = executable and source["id"] in historical_source_ids
        if source_had_conversion and mapping:
            raise StaleReport(
                "A source with conversion history cannot be selected in a later batch"
            )
        if source["id"] in active_replaced_source_ids:
            warnings.append("Already represented by an active conversion opening.")
            outcome = "converted" if source["active"] else "inactive"
        elif source_had_conversion:
            warnings.append(
                "Conversion history exists; the current legacy representation remains unchanged."
            )
            outcome = "unresolved"
        elif not mapping:
            warnings.append("No explicit source mapping; retains live treatment.")
        else:
            required_fields = ("instrument_id", "specification_id")
            if executable or source["portfolio_id"] is None:
                required_fields += ("investment_account_id",)
            else:
                required_fields += ("portfolio_id", "account_id")
            if any(getattr(mapping, field) is None for field in required_fields) or not mapping.identity_confirmed:
                warnings.append("Exact container, instrument and specification identity must be confirmed.")
            if mapping.beneficial_ownership != "personal":
                warnings.append("Personal beneficial ownership is not confirmed; retains live treatment.")
            if source["cost_basis_cents"] == 0 and not mapping.zero_basis_reviewed:
                warnings.append("Legacy zero basis requires explicit review, even when basis is unknown.")
            if mapping.investment_account_id is not None:
                container = indexes["investment_accounts"][mapping.investment_account_id]
                if not all((container["active"], indexes["portfolios"][container["portfolio_id"]]["active"],
                            indexes["accounts"][container["account_id"]]["active"])):
                    warnings.append("Inactive target metadata cannot receive an opening snapshot.")
            elif source["portfolio_id"] is not None:
                if not indexes["portfolios"][source["portfolio_id"]]["active"]:
                    warnings.append("An archived portfolio cannot receive a holding.")
                if mapping.account_id is not None and not indexes["accounts"][mapping.account_id]["active"]:
                    warnings.append("An inactive Account cannot be reviewed as its cash ledger.")
            if mapping.instrument_id is not None and not indexes["instruments"][mapping.instrument_id]["active"]:
                warnings.append("Instrument is inactive.")
            if mapping.specification_id is not None:
                spec = indexes["instrument_specifications"][mapping.specification_id]
                if spec["currency"] != "USD" or spec["asset_type"] not in ("STOCK", "ETF"):
                    warnings.append("Only USD long stock/ETF opening snapshots are in scope.")
            if source["quantity_units"] <= 0:
                warnings.append("A positive long quantity is required.")
        if source["id"] not in active_replaced_source_ids and not source_had_conversion:
            outcome = "inactive" if not source["active"] else ("unresolved" if warnings else "eligible")
        basis_status = mapping.basis_status if mapping else "unverified"
        sources.append({
            "source": source, "mapping": mapping.model_dump(mode="json") if mapping else None,
            "outcome": outcome, "warnings": warnings,
            "current_value_cents": (
                0 if source["id"] in active_replaced_source_ids
                else source["current_value_cents"] if source["active"] and not source["review_pending"] else 0
            ),
            "current_holding_cents": current_opening_values.get(source["id"], 0),
            "basis_status": basis_status,
            "basis_cents": None if basis_status == "unknown" else source["cost_basis_cents"],
            "valuation": {
                "value_cents": source["current_value_cents"],
                "as_of": mapping.valuation_as_of.isoformat() if mapping and mapping.valuation_as_of else None,
                "evidence": mapping.valuation_evidence if mapping else None,
                "provenance": "legacy_user_entered",
                "warning": "Not a current market quote; record edit time is not valuation time.",
            },
        })

    by_source = {row["source"]["id"]: row for row in sources}
    balances = {row["id"]: row["opening_balance_cents"] for row in snapshot["accounts"]}
    for transaction in snapshot["transactions"]:
        _require(indexes["accounts"], transaction["account_id"])
        if transaction["deleted_at"] is None:
            direction = {"Income": 1, "Expense": -1}.get(transaction["transaction_type"])
            if direction is None:
                raise ValueError("Unknown transaction direction")
            balances[transaction["account_id"]] += direction * transaction["amount_cents"]
    if executable:
        for entry in conversion_cash_entries:
            balances[entry["account_id"]] += entry["delta_cents"]
    accounts = []
    for account in snapshot["accounts"]:
        account_id = account["id"]
        item = evidence.get(account_id)
        new_group = {source_id for source_id, target in targets.items() if target == account_id}
        history = account_conversion_history(conversion_state, account_id) if executable else {
            "source_ids": [], "opening_position_ids": [], "cash_entry_ids": [],
            "active_source_ids": [], "previous_correction_cents": 0,
        }
        group = new_group | set(history["source_ids"])
        declared_group = set(item.source_ids) if item else set()
        warnings = []
        correction = 0
        if new_group or declared_group or item:
            if not item or not item.complete or not (item.evidence or "").strip():
                warnings.append("Complete account-level evidence is required; no partial correction.")
            if not item or item.balance_meaning == "unknown":
                warnings.append("Cash versus combined balance meaning remains unresolved.")
            if group != declared_group:
                warnings.append("Declared source list must exactly match all new and previously converted sources for this account.")
            if executable and item:
                try:
                    validate_prior_account_evidence(item.model_dump(), history)
                except ValueError as exc:
                    warnings.append(str(exc))
            if any(by_source[source_id]["outcome"] not in ("eligible", "converted")
                   for source_id in group | declared_group):
                warnings.append("An unresolved or inactive member blocks the entire account correction.")
            if item and item.balance_meaning in ("cash_only", "combined"):
                if item.cash_cents is None or item.cash_cents < 0:
                    warnings.append("Evidence must specify nonnegative exact cash cents.")
                else:
                    # Prior opening values are already represented separately.
                    # Only newly mapped legacy values can still overlap current cash.
                    included_value = sum(
                        indexes["investments"][source_id]["current_value_cents"]
                        for source_id in declared_group - set(history["source_ids"])
                    )
                    expected = item.cash_cents + (included_value if item.balance_meaning == "combined" else 0)
                    if expected != balances[account_id]:
                        warnings.append("Evidence does not reconcile exactly to the current ledger balance.")
                    elif item.balance_meaning == "combined":
                        correction = -included_value
            if warnings:
                correction = 0
                for source_id in new_group:
                    row = by_source[source_id]
                    if row["outcome"] != "inactive":
                        row["outcome"] = "unresolved"
                    row["warnings"].extend(warnings)
        else:
            warnings.append("Account meaning not reviewed; current balance remains unchanged.")
        accounts.append({
            "account": account, "evidence": item.model_dump(mode="json") if item else None,
            "prior_conversions": history,
            "current_balance_cents": balances[account_id],
            "proposed_balance_cents": balances[account_id] + correction,
            "correction_cents": correction, "warnings": warnings,
        })
    for row in sources:
        eligible = row["outcome"] == "eligible"
        row["proposed_legacy_cents"] = 0 if eligible else row["current_value_cents"]
        row["proposed_holding_cents"] = (
            row["current_holding_cents"]
            + (row["source"]["current_value_cents"] if eligible else 0)
        )
        row["delta_cents"] = row["proposed_holding_cents"] - row["current_holding_cents"] - row["current_value_cents"] if eligible else 0
    debt = sum(row["balance_cents"] for row in snapshot["debts"] if row["active"])
    current = {
        "account_balance_cents": sum(balances.values()),
        "legacy_investment_cents": sum(row["current_value_cents"] for row in sources),
        "holding_value_cents": sum(row["current_holding_cents"] for row in sources),
        "debt_balance_cents": debt,
    }
    proposed = {
        "account_balance_cents": sum(row["proposed_balance_cents"] for row in accounts),
        "legacy_investment_cents": sum(row["proposed_legacy_cents"] for row in sources),
        "holding_value_cents": sum(row["proposed_holding_cents"] for row in sources),
        "debt_balance_cents": debt,
    }
    for total in (current, proposed):
        total["net_worth_cents"] = total["account_balance_cents"] + total["legacy_investment_cents"] + total["holding_value_cents"] - total["debt_balance_cents"]
    report = {
        "format": (
            "serenity-conversion-execution-report" if executable
            else "serenity-reconciliation-preview"
        ), "format_version": 2 if executable else 1,
        "algorithm_version": "conversion-execution-2" if executable else None,
        "executable": bool(executable),
        "conversion_fingerprint": _fingerprint(conversion_state),
        "owner_id": owner_id, "captured_at": captured_at,
        "source_fingerprint": _fingerprint(snapshot), "dependencies": snapshot,
        "sources": sources, "accounts": accounts, "current": current, "proposed": proposed,
        "delta_cents": proposed["net_worth_cents"] - current["net_worth_cents"],
        "explanations": [
            {"account_id": row["account"]["id"], "delta_cents": row["correction_cents"],
             "reason": (
                 "Evidence-backed duplicate-count correction only; not income, expense or investment loss."
                 if row["correction_cents"] else "Account ledger balance retained unchanged."
             )}
            for row in accounts
        ] + [
            {"source_id": row["source"]["id"], "delta_cents": 0,
             "reason": (
                 "Existing conversion opening remains represented once in current and proposed holdings."
                 if row["outcome"] == "converted" else {
                     "eligible": "Original value moves from legacy to hypothetical holding exactly once.",
                     "inactive": "Inactive source remains excluded from both totals.",
                     "unresolved": "Unresolved source retains its existing legacy value; no replacement counted.",
                 }[row["outcome"]]
             )}
            for row in sources
        ] + [{"delta_cents": 0, "reason": "Active debt balances are subtracted unchanged in both totals."}],
        "warnings": [
            "Read-only hypothetical preview. No conversion, approval, posting or live valuation change.",
            "Unresolved sources retain live treatment, including any unresolved overlap.",
            "Eligible replacements preserve original typed values exactly; no price refresh or invented acquisition date.",
            "Account balances follow the live formula, which includes inactive account ledgers; inactive investments remain excluded.",
            "Account completeness is user-attested; legacy investments have no stored account link.",
            "Cancellation discards this report locally. Export is not an import, backup or execution authorization.",
        ] + ([
            "Legacy format 1 semantics do not include existing conversion ledger balances; use current dashboard totals for present value.",
            "This legacy preview remains review-only and cannot be approved for execution.",
        ] if any(conversion_state.values()) and not executable else []) + ([
            "Existing active conversion openings and cash-ledger entries are included in executable batch totals.",
            "Prior openings and cash corrections require exact references and completeness attestation; only new legacy values can receive an overlap correction.",
        ] if executable and any(conversion_state.values()) else []),
    }
    return {"report": report, "report_token": _sign(report)}


def build_execution_preview(db: Session, owner_id: str, data: PreviewRequest) -> dict:
    """Create a distinct, signed v2 report; v1 preview tokens remain review-only."""
    lock_owner_financial_writes(db, owner_id)
    try:
        return build_preview(db, owner_id, data, executable=True)
    finally:
        # Consistent, serialized capture only: never persist a preview.
        db.rollback()


def verify_report(db: Session, owner_id: str, token: str) -> dict:
    report = _decode(token, owner_id)
    if report["format_version"] == 2:
        snapshot = _execution_snapshot(db, owner_id)
        stale = report["source_fingerprint"] != _fingerprint(snapshot)
    else:
        snapshot = capture_dependencies(db, owner_id)
        conversion_state = _conversion_snapshot(db, owner_id)
        conversion_fingerprint = report.get("conversion_fingerprint")
        stale = report["source_fingerprint"] != _fingerprint(snapshot)
        if conversion_fingerprint is None:
            stale = stale or any(conversion_state.values())
        else:
            stale = stale or conversion_fingerprint != _fingerprint(conversion_state)
    return {"valid": True, "stale": stale, "report": report}


def export_report(db: Session, owner_id: str, token: str) -> dict:
    result = verify_report(db, owner_id, token)
    if result["stale"]:
        raise StaleReport("Preview is stale; regenerate before exporting")
    return {"report": result["report"], "report_token": token}