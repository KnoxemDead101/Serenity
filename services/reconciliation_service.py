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

from sqlalchemy import Boolean, String, cast, func, literal, select, union_all
from sqlalchemy.orm import Session

from auth import _secret
from models.account import Account, utc_now
from models.bill import Bill
from models.business import Business
from models.debt import Debt
from models.dependent import Dependent
from models.income_profile import IncomeProfile
from models.instrument import Instrument, InstrumentSpecification
from models.investment import Investment
from models.portfolio import InvestmentAccount, Portfolio
from models.transaction import Transaction
from models.transaction_correction import TransactionCorrection
from schemas.reconciliation import PreviewRequest
from services.ownership import require_owner_id


class ReconciliationNotFound(ValueError):
    pass


class StaleReport(ValueError):
    pass


DEPENDENCIES = (
    Account, Bill, Business, Debt, Dependent, IncomeProfile, Instrument,
    InstrumentSpecification, Investment, Portfolio, InvestmentAccount,
    Transaction, TransactionCorrection,
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
    signature = hmac.new(_secret(), b"serenity-reconciliation-v1:" + payload.encode("ascii"), hashlib.sha256).hexdigest()
    return payload + "." + signature


def _decode(token: str, owner_id: str) -> dict:
    secret = _secret()
    try:
        payload, signature = token.split(".")
        expected = hmac.new(secret, b"serenity-reconciliation-v1:" + payload.encode("ascii"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise ValueError("Invalid signature")
        report = json.loads(base64.b64decode(payload, altchars=b"-_", validate=True))
        if report["owner_id"] != require_owner_id(owner_id) or report["format_version"] != 1:
            raise ValueError("Wrong report scope")
        return report
    except (ValueError, KeyError, TypeError, UnicodeError) as exc:
        raise ReconciliationNotFound("Reconciliation report not found") from exc


def build_preview(db: Session, owner_id: str, data: PreviewRequest) -> dict:
    owner_id = require_owner_id(owner_id)
    captured_at = utc_now().isoformat()
    snapshot = capture_dependencies(db, owner_id)
    indexes = {name: {row["id"]: row for row in rows} for name, rows in snapshot.items()}
    mappings = _unique(data.mappings, "source_id")
    evidence = _unique(data.accounts, "account_id")
    targets = {}
    # Validate every supplied identifier, including inactive/unresolved inputs.
    for mapping in data.mappings:
        source = _require(indexes["investments"], mapping.source_id)
        for field, table in (
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
            if mapping.portfolio_id != source["portfolio_id"] or mapping.investment_account_id is not None:
                raise ReconciliationNotFound("Reconciliation resource not found")
            _require(indexes["portfolios"], mapping.portfolio_id)
            if mapping.account_id is not None:
                _require(indexes["accounts"], mapping.account_id)
                targets[mapping.source_id] = mapping.account_id
        elif mapping.portfolio_id is not None or mapping.account_id is not None:
            raise ReconciliationNotFound("Reconciliation resource not found")
        if mapping.investment_account_id is not None:
            container = indexes["investment_accounts"][mapping.investment_account_id]
            if source["review_pending"] and source["investment_account_id"] != container["id"]:
                raise ReconciliationNotFound("Reconciliation resource not found")
            _require(indexes["accounts"], container["account_id"])
            _require(indexes["portfolios"], container["portfolio_id"])
            targets[mapping.source_id] = container["account_id"]
    declared = {}
    for item in data.accounts:
        _require(indexes["accounts"], item.account_id)
        if len(set(item.source_ids)) != len(item.source_ids):
            raise ValueError("Duplicate source_ids in account evidence")
        for source_id in item.source_ids:
            _require(indexes["investments"], source_id)
            if source_id in declared:
                raise ValueError("A source cannot be declared for multiple accounts")
            declared[source_id] = item.account_id
            if source_id in targets and targets[source_id] != item.account_id:
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
        if not mapping:
            warnings.append("No explicit source mapping; retains live treatment.")
        else:
            required = ("account_id" if source["portfolio_id"] is not None else "investment_account_id",
                        "instrument_id", "specification_id")
            if any(getattr(mapping, field) is None for field in required) or not mapping.identity_confirmed:
                warnings.append("Account, instrument and specification identity must be confirmed.")
            if mapping.beneficial_ownership != "personal":
                warnings.append("Personal beneficial ownership is not confirmed; retains live treatment.")
            if source["cost_basis_cents"] == 0 and not mapping.zero_basis_reviewed:
                warnings.append("Legacy zero basis requires explicit review, even when basis is unknown.")
            if mapping.investment_account_id is not None:
                container = indexes["investment_accounts"][mapping.investment_account_id]
                if not all((container["active"], indexes["portfolios"][container["portfolio_id"]]["active"],
                            indexes["accounts"][container["account_id"]]["active"])):
                    warnings.append("Inactive target metadata cannot receive an opening snapshot.")
            if source["portfolio_id"] is not None:
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
        outcome = "inactive" if not source["active"] else ("unresolved" if warnings else "eligible")
        basis_status = mapping.basis_status if mapping else "unverified"
        sources.append({
            "source": source, "mapping": mapping.model_dump(mode="json") if mapping else None,
            "outcome": outcome, "warnings": warnings,
            "current_value_cents": source["current_value_cents"] if source["active"] and not source["review_pending"] else 0,
            "basis_status": basis_status,
            "basis_cents": None if basis_status == "unknown" else source["cost_basis_cents"],
            "valuation": {
                "value_cents": source["current_value_cents"],
                "as_of": mapping.valuation_as_of.isoformat() if mapping and mapping.valuation_as_of else None,
                "evidence": mapping.valuation_evidence if mapping else None,
                "provenance": "original_user_entered_value",
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
    accounts = []
    for account in snapshot["accounts"]:
        account_id = account["id"]
        item = evidence.get(account_id)
        group = {source_id for source_id, target in targets.items() if target == account_id}
        declared_group = set(item.source_ids) if item else set()
        warnings = []
        correction = 0
        if group or declared_group or item:
            if not item or not item.complete or not (item.evidence or "").strip():
                warnings.append("Complete account-level evidence is required; no partial correction.")
            if not item or item.balance_meaning == "unknown":
                warnings.append("Cash versus combined balance meaning remains unresolved.")
            if group != declared_group:
                warnings.append("Declared source list must exactly match all mapped sources for this account.")
            if any(by_source[source_id]["outcome"] != "eligible" for source_id in group | declared_group):
                warnings.append("An unresolved or inactive member blocks the entire account correction.")
            if item and item.balance_meaning in ("cash_only", "combined"):
                if item.cash_cents is None or item.cash_cents < 0:
                    warnings.append("Evidence must specify nonnegative exact cash cents.")
                else:
                    included_value = sum(indexes["investments"][source_id]["current_value_cents"] for source_id in declared_group)
                    expected = item.cash_cents + (included_value if item.balance_meaning == "combined" else 0)
                    if expected != balances[account_id]:
                        warnings.append("Evidence does not reconcile exactly to the current ledger balance.")
                    elif item.balance_meaning == "combined":
                        correction = -included_value
            if warnings:
                correction = 0
                for source_id in group:
                    row = by_source[source_id]
                    if row["outcome"] != "inactive":
                        row["outcome"] = "unresolved"
                    row["warnings"].extend(warnings)
        else:
            warnings.append("Account meaning not reviewed; current balance remains unchanged.")
        accounts.append({
            "account": account, "evidence": item.model_dump(mode="json") if item else None,
            "current_balance_cents": balances[account_id],
            "proposed_balance_cents": balances[account_id] + correction,
            "correction_cents": correction, "warnings": warnings,
        })
    for row in sources:
        eligible = row["outcome"] == "eligible"
        row["proposed_legacy_cents"] = 0 if eligible else row["current_value_cents"]
        row["proposed_holding_cents"] = row["source"]["current_value_cents"] if eligible else 0
        row["delta_cents"] = row["proposed_holding_cents"] - row["current_value_cents"]
    debt = sum(row["balance_cents"] for row in snapshot["debts"] if row["active"])
    current = {
        "account_balance_cents": sum(balances.values()),
        "legacy_investment_cents": sum(row["current_value_cents"] for row in sources),
        "holding_value_cents": 0, "debt_balance_cents": debt,
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
        "format": "serenity-reconciliation-preview", "format_version": 1,
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
            {"source_id": row["source"]["id"], "delta_cents": row["delta_cents"],
             "reason": {
                 "eligible": ("Uncounted draft would enter holdings only after approved review."
                              if row["source"]["review_pending"] else
                              "Original value moves from legacy to hypothetical holding exactly once."),
                 "inactive": "Inactive source remains excluded from both totals.",
                 "unresolved": ("Unresolved draft remains uncounted."
                                if row["source"]["review_pending"] else
                                "Unresolved source retains its existing legacy value; no replacement counted."),
             }[row["outcome"]]}
            for row in sources
        ] + [{"delta_cents": 0, "reason": "Active debt balances are subtracted unchanged in both totals."}],
        "warnings": [
            "Read-only hypothetical preview. No conversion, approval, posting or live valuation change.",
            "Unresolved existing sources retain live treatment; unresolved drafts remain uncounted.",
            "Eligible replacements preserve original typed values exactly; no price refresh or invented acquisition date.",
            "Account balances follow the live formula, which includes inactive account ledgers; inactive investments remain excluded.",
            "Account completeness is user-attested; a portfolio assignment does not certify account meaning or beneficial ownership.",
            "Cancellation discards this report locally. Export is not an import, backup or execution authorization.",
        ],
    }
    return {"report": report, "report_token": _sign(report)}


def verify_report(db: Session, owner_id: str, token: str) -> dict:
    report = _decode(token, owner_id)
    stale = report["source_fingerprint"] != _fingerprint(capture_dependencies(db, owner_id))
    return {"valid": True, "stale": stale, "report": report}


def export_report(db: Session, owner_id: str, token: str) -> dict:
    result = verify_report(db, owner_id, token)
    if result["stale"]:
        raise StaleReport("Preview is stale; regenerate before exporting")
    return {"report": result["report"], "report_token": token}