"""Transactional owner-scoped conversion approval, execution and reversal.

Real execution is deliberately unavailable until this application has an
off-host-backup verifier. Synthetic execution is limited to isolated tests:
the SQLite conversion API suite or one explicitly opted-in disposable
PostgreSQL fixture test. It is never a production backup substitute.
"""

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import make_url, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import Account, utc_now
from models.conversion import (
    CashReconciliationEntry, ConversionEvent, OpeningPosition,
    ReconciliationApproval, ValuationEligibility,
)
from models.instrument import Instrument, InstrumentSpecification
from models.investment import Investment
from models.portfolio import InvestmentAccount, Portfolio
from services import reconciliation_service
from services.financial_write_lock import lock_owner_financial_writes
from services.ownership import require_owner_id


class ConversionNotFound(ValueError):
    pass


class ConversionConflict(ValueError):
    pass


class BackupEvidenceUnavailable(RuntimeError):
    pass


def _validate_report_totals(report):
    current = report["current"]
    proposed = report["proposed"]
    sources = report["sources"]
    accounts = report["accounts"]
    deps = report["dependencies"]
    debt = sum(row["balance_cents"] for row in deps["debts"] if row["active"])
    expected_current = {
        "account_balance_cents": sum(row["current_balance_cents"] for row in accounts),
        "legacy_investment_cents": sum(row["current_value_cents"] for row in sources),
        "holding_value_cents": sum(row.get("current_holding_cents", 0) for row in sources),
        "debt_balance_cents": debt,
    }
    expected_proposed = {
        "account_balance_cents": sum(row["proposed_balance_cents"] for row in accounts),
        "legacy_investment_cents": sum(row["proposed_legacy_cents"] for row in sources),
        "holding_value_cents": sum(row["proposed_holding_cents"] for row in sources),
        "debt_balance_cents": debt,
    }
    for label, actual, expected in (
        ("current", current, expected_current), ("proposed", proposed, expected_proposed),
    ):
        if any(actual.get(key) != value for key, value in expected.items()):
            raise ValueError(f"{label.title()} report components do not match their source rows")
        net_worth = (expected["account_balance_cents"] + expected["legacy_investment_cents"]
                     + expected["holding_value_cents"] - expected["debt_balance_cents"])
        if actual.get("net_worth_cents") != net_worth:
            raise ValueError(f"{label.title()} report net worth does not reconcile")
        if any(type(value) is not int or not -(2**63) <= value < 2**63
               for value in (*expected.values(), net_worth)):
            raise ValueError("Report totals exceed the supported signed-cent range")
    if report["delta_cents"] != proposed["net_worth_cents"] - current["net_worth_cents"]:
        raise ValueError("Report delta does not reconcile")
    if type(report["delta_cents"]) is not int or not -(2**63) <= report["delta_cents"] < 2**63:
        raise ValueError("Report delta exceeds the supported signed-cent range")
    if any(type(row["correction_cents"]) is not int
           or not -(2**63) <= row["correction_cents"] < 2**63 for row in accounts):
        raise ValueError("Account correction exceeds the supported signed-cent range")


def _canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def _aware(value):
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _lock_owner(db: Session, owner_id: str):
    """Join the lock protocol shared by every mediated financial writer."""
    try:
        lock_owner_financial_writes(db, owner_id)
        # A caller may have preloaded rows before a competing writer committed.
        # Dependency capture and source reads must use the locked current state.
        db.expire_all()
    except RuntimeError as exc:
        raise ConversionConflict("This database has no supported owner write lock") from exc


def _backup_gate(db, request_test_mode, reference, cutoff, rollback_deadline):
    marker = os.getenv("PYTEST_CURRENT_TEST", "").partition(" (")[0]
    sqlite_url = db.get_bind().url
    sqlite_database = sqlite_url.database
    isolated_sqlite = sqlite_database in (None, "", ":memory:")
    configured_sqlite = os.getenv("SERENITY_CONVERSION_SQLITE_TEST_DATABASE_URL")
    if configured_sqlite and sqlite_database:
        fixture_url = make_url(configured_sqlite)
        fixture_path = Path(sqlite_database).resolve()
        isolated_sqlite = (
            fixture_url == sqlite_url
            and fixture_path.name == "disposable-conversion.db"
            and any(parent.name.startswith("pytest-") for parent in fixture_path.parents)
        )
    sqlite_test_mode = (
        request_test_mode is True
        and os.getenv("SERENITY_CONVERSION_TEST_MODE") == "1"
        and marker.startswith("tests/test_conversion_api.py::")
        and db.get_bind().dialect.name == "sqlite"
        and isolated_sqlite
        and reference.startswith("synthetic://")
    )
    postgres_test_mode = False
    configured_url = os.getenv("SERENITY_CONVERSION_POSTGRES_TEST_DATABASE_URL")
    if (
        request_test_mode is True
        and os.getenv("SERENITY_CONVERSION_TEST_MODE") == "1"
        and os.getenv("SERENITY_CONVERSION_POSTGRES_TEST_MODE") == "1"
        and marker == (
            "tests/test_money_postgres.py::"
            "test_postgres_two_owner_conversion_execution_proof"
        )
        and configured_url
        and reference.startswith("synthetic://")
        and db.get_bind().dialect.name == "postgresql"
    ):
        try:
            expected = make_url(configured_url)
            actual = db.get_bind().url
            socket_dir = expected.query.get("host")
            socket_path = Path(socket_dir) if isinstance(socket_dir, str) else None
            safe_socket = (
                socket_path is not None
                and socket_path.is_absolute()
                and socket_path.name == "socket"
                and socket_path.parent.name.startswith("isolated-money-pg")
            )
            exact_fixture_url = (
                actual.drivername == "postgresql+psycopg"
                and expected.drivername in ("postgresql", "postgresql+psycopg")
                and actual.username == expected.username == "moneytest"
                and actual.database == expected.database == "postgres"
                and actual.host is None
                and actual.query.get("host") == expected.query.get("host")
                and actual.query.get("port") == expected.query.get("port") == "55433"
                and safe_socket
            )
            if exact_fixture_url:
                connection_identity = db.execute(text(
                    "SELECT current_database(), current_user, inet_server_addr()"
                )).one()
                postgres_test_mode = (
                    connection_identity[0] == "postgres"
                    and connection_identity[1] == "moneytest"
                    and connection_identity[2] is None
                )
        except Exception:
            postgres_test_mode = False

    if not (sqlite_test_mode or postgres_test_mode):
        # No production backup evidence provider exists in this implementation.
        raise BackupEvidenceUnavailable("Verified off-host backup evidence is required")
    now = utc_now()
    if not _aware(cutoff) <= _aware(now) or (_aware(now) - _aware(cutoff)).total_seconds() > 86400:
        raise BackupEvidenceUnavailable("Synthetic backup evidence cutoff is invalid or stale")
    if not _aware(now) < _aware(rollback_deadline):
        raise ConversionConflict("Rollback deadline must be in the future")
    if (_aware(rollback_deadline) - _aware(now)).total_seconds() > 30 * 86400:
        raise ConversionConflict("Rollback deadline exceeds the supported 30-day window")


def _decode_execution_report(db, owner_id, token, digest):
    report = reconciliation_service._decode(token, owner_id)
    if report.get("format_version") != 2 or report.get("executable") is not True:
        raise ValueError("Only a version 2 execution report can be approved")
    canonical = _canonical(report)
    actual = hashlib.sha256(canonical).hexdigest()
    if not hmac.compare_digest(actual, digest):
        raise ValueError("Report digest does not match the exact signed report")
    current = reconciliation_service._execution_snapshot(db, owner_id)
    if report.get("source_fingerprint") != reconciliation_service._fingerprint(current):
        raise ConversionConflict("Execution report is stale; regenerate and reapprove")
    return report, canonical, actual


def _validate_account_groups(report, selected_source_ids, containers):
    source_rows = {row["source"]["id"]: row for row in report["sources"]}
    account_rows = {row["account"]["id"]: row for row in report["accounts"]}
    source_account = {}
    for source_id, row in source_rows.items():
        mapping = row["mapping"]
        if mapping and mapping.get("investment_account_id") is not None:
            container = containers.get(mapping["investment_account_id"])
            if container is None:
                raise ValueError("Execution report contains an invalid container")
            source_account[source_id] = container["account_id"]
    prior_state = report["dependencies"].get("conversion_state", {})
    for position in prior_state.get("opening_positions", []):
        source_account[position["source_investment_id"]] = position["cash_account_id"]

    for account_id in {source_account[source_id] for source_id in selected_source_ids}:
        account_row = account_rows.get(account_id)
        evidence = account_row.get("evidence") if account_row else None
        if (not evidence or not evidence.get("complete")
                or not (evidence.get("evidence") or "").strip()
                or evidence.get("balance_meaning") not in ("cash_only", "combined")):
            raise ValueError("Every selected account requires explicit complete evidence")
        group = {source_id for source_id, target in source_account.items() if target == account_id}
        history = reconciliation_service.account_conversion_history(prior_state, account_id)
        reconciliation_service.validate_prior_account_evidence(evidence, history)
        declared = set(evidence.get("source_ids") or [])
        if group != declared:
            raise ValueError("Account evidence must enumerate the exact complete source group")
        if any(source_rows[source_id]["outcome"] not in ("eligible", "converted")
               for source_id in group):
            raise ValueError("Unresolved or inactive group members block conversion")
        cash_cents = evidence.get("cash_cents")
        if type(cash_cents) is not int or cash_cents < 0:
            raise ValueError("Account evidence must specify exact nonnegative cash cents")
        original_value = sum(source_rows[source_id]["source"]["current_value_cents"]
                             for source_id in declared - set(history["source_ids"]))
        represented = cash_cents + (
            original_value if evidence["balance_meaning"] == "combined" else 0
        )
        expected_correction = (
            -original_value if evidence["balance_meaning"] == "combined" else 0
        )
        if represented != account_row["current_balance_cents"]:
            raise ValueError("Account evidence does not reconcile exactly to the current balance")
        if account_row["correction_cents"] != expected_correction:
            raise ValueError("Account correction does not match the complete source group")
        if account_row["proposed_balance_cents"] != (
            account_row["current_balance_cents"] + expected_correction
        ):
            raise ValueError("Proposed account balance does not match its correction")


def approve(db: Session, owner_id: str, actor_id: str, data) -> dict:
    owner_id = require_owner_id(owner_id)
    _lock_owner(db, owner_id)
    try:
        report, canonical, digest = _decode_execution_report(
            db, owner_id, data.report_token, data.report_sha256
        )
        if not data.confirm_approval:
            raise ValueError("Explicit approval confirmation is required")
        _validate_report_totals(report)
        _backup_gate(db, data.test_only_synthetic, data.backup_evidence_reference,
                     data.backup_cutoff, data.rollback_deadline)

        sources = {row["source"]["id"]: row for row in report["sources"]}
        eligible = {sid for sid, row in sources.items() if row["outcome"] == "eligible"}
        chosen = data.selected_source_ids
        if len(set(chosen)) != len(chosen) or set(chosen) != eligible or not chosen:
            raise ValueError("Approval must select the exact complete eligible source set")
        dependencies = report["dependencies"]
        containers = {row["id"]: row for row in dependencies["investment_accounts"]}
        _validate_account_groups(report, chosen, containers)
        account_by_source = {}
        for sid in chosen:
            mapping = sources[sid]["mapping"]
            if not mapping or mapping.get("investment_account_id") is None:
                raise ValueError("Every selected source requires an explicit container mapping")
            account_id = containers[mapping["investment_account_id"]]["account_id"]
            account_by_source[sid] = account_id

        account_rows = {row["account"]["id"]: row for row in report["accounts"]}
        affected = set(account_by_source.values())
        expected_corrections = {
            str(account_id): account_rows[account_id]["correction_cents"]
            for account_id in affected
        }
        if data.account_corrections_cents != expected_corrections:
            raise ValueError("Account corrections must exactly match the reviewed report")
        approval = ReconciliationApproval(
            owner_id=owner_id, canonical_report=canonical, report_format_version=2,
            algorithm_version=report["algorithm_version"], report_sha256=digest,
            signed_token_evidence=data.report_token,
            preview_cutoff=datetime.fromisoformat(report["captured_at"]),
            source_fingerprint=report["source_fingerprint"], approving_actor_id=actor_id,
            approved_source_ids=json.dumps(sorted(chosen)),
            account_corrections_cents=json.dumps(expected_corrections, sort_keys=True),
            before_component_totals_cents=json.dumps(report["current"], sort_keys=True),
            after_component_totals_cents=json.dumps(report["proposed"], sort_keys=True),
            expected_delta_cents=report["delta_cents"],
            backup_evidence_reference=data.backup_evidence_reference,
            backup_cutoff=_aware(data.backup_cutoff),
            rollback_deadline=_aware(data.rollback_deadline),
            state="approved",
        )
        db.add(approval)
        db.flush()
        result = {"approval_id": approval.id, "report_sha256": digest, "state": approval.state}
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise ConversionConflict("This report already has an approval or conflicts with history") from exc
    except Exception:
        db.rollback()
        raise


def _approval(db, owner_id, approval_id):
    row = db.execute(select(ReconciliationApproval).where(
        ReconciliationApproval.owner_id == owner_id,
        ReconciliationApproval.id == approval_id,
    ).with_for_update().execution_options(populate_existing=True)).scalar_one_or_none()
    if row is None:
        raise ConversionNotFound("Conversion approval not found")
    return row


def _account_balance(db, owner_id, account_id):
    account = db.execute(select(Account).where(
        Account.owner_id == owner_id, Account.id == account_id
    )).scalar_one_or_none()
    if account is None:
        raise ConversionNotFound("Conversion account not found")
    from models.transaction import Transaction
    from models.conversion import CashReconciliationEntry
    balance = account.opening_balance_cents
    for tx in db.execute(select(Transaction).where(
        Transaction.owner_id == owner_id, Transaction.account_id == account_id,
        Transaction.deleted_at.is_(None),
    )).scalars():
        balance += tx.amount_cents if tx.transaction_type == "Income" else -tx.amount_cents
    balance += sum(db.execute(select(CashReconciliationEntry.delta_cents).where(
        CashReconciliationEntry.owner_id == owner_id,
        CashReconciliationEntry.account_id == account_id,
    )).scalars())
    return balance


def _compute_component_totals(db: Session, owner_id: str) -> dict:
    """Recompute exact totals via the same account/finance readers as the dashboard."""
    from services import account_service, dashboard_service, finance_service, portfolio_service

    accounts = account_service.list_accounts(db, owner_id)
    account_balance = account_service.total_balance_cents(accounts, db)
    investments = finance_service.list_investments(db, owner_id)
    legacy = portfolio_service.eligible_legacy_investments(db, owner_id, investments)
    _, openings = portfolio_service.selected_valuation_records(db, owner_id)
    legacy_cents = sum(row.current_value_cents for row in legacy)
    holding_cents = sum(row.original_entered_value_cents for row in openings)
    debt_cents = finance_service.total_debt_balance_cents(
        finance_service.list_debts(db, owner_id)
    )
    net_worth = dashboard_service.calculate_net_worth_cents(
        account_balance, legacy_cents + holding_cents, debt_cents,
    )
    return {
        "account_balance_cents": account_balance,
        "legacy_investment_cents": legacy_cents,
        "holding_value_cents": holding_cents,
        "debt_balance_cents": debt_cents,
        "net_worth_cents": net_worth,
    }


def _after_conversion_ledger_writes():
    """Failure-injection seam used to verify atomic rollback between ledger writes."""


def _reversal_dependencies(db: Session, owner_id: str) -> dict:
    """Committed post-write baseline; events are checked independently."""
    snapshot = reconciliation_service._execution_snapshot(db, owner_id)
    snapshot["conversion_state"].pop("conversion_events", None)
    return snapshot


def _blocking_references(baseline: dict, current: dict) -> dict:
    references = {}
    for snapshot in (baseline, current):
        for table, rows in snapshot.items():
            if table == "conversion_state":
                for name, records in rows.items():
                    references.setdefault(name, [[], []])
            elif isinstance(rows, list):
                references.setdefault(table, [[], []])
    for index, snapshot in enumerate((baseline, current)):
        flattened = {**snapshot, **snapshot.get("conversion_state", {})}
        for table in references:
            references[table][index] = {row["id"]: row for row in flattened.get(table, [])}
    return {
        table: sorted(row_id for row_id in before.keys() | after.keys()
                      if before.get(row_id) != after.get(row_id))
        for table, (before, after) in references.items()
        if before != after
    }


def execute(db: Session, owner_id: str, actor_id: str, approval_id: int, data) -> dict:
    owner_id = require_owner_id(owner_id)
    payload_hash = hashlib.sha256(_canonical({
        "approval_id": approval_id, "idempotency_key": data.idempotency_key,
        "confirm_execute": data.confirm_execute,
    })).hexdigest()
    _lock_owner(db, owner_id)
    try:
        approval = _approval(db, owner_id, approval_id)
        if not data.confirm_execute:
            raise ValueError("Explicit final execution confirmation is required")
        if approval.state == "executed":
            if (approval.execution_idempotency_key != data.idempotency_key
                    or approval.execution_payload_sha256 != payload_hash):
                raise ConversionConflict("Approval was executed with a different idempotency binding")
            event = db.execute(select(ConversionEvent).where(
                ConversionEvent.owner_id == owner_id, ConversionEvent.approval_id == approval_id,
                ConversionEvent.event_kind == "executed",
            )).scalar_one()
            result = _event_result(event)
            db.commit()
            return result
        if approval.state != "approved":
            raise ConversionConflict("Approval is no longer executable")
        if _aware(utc_now()) > _aware(approval.rollback_deadline):
            approval.state = "expired"
            db.commit()
            raise ConversionConflict("Approval rollback window expired")
        _backup_gate(db, os.getenv("SERENITY_CONVERSION_TEST_MODE") == "1",
                     approval.backup_evidence_reference, approval.backup_cutoff,
                     approval.rollback_deadline)
        report = json.loads(approval.canonical_report)
        current = reconciliation_service._execution_snapshot(db, owner_id)
        if approval.source_fingerprint != reconciliation_service._fingerprint(current):
            raise ConversionConflict("Approved report is stale; obtain a new approval")
        before_totals = _compute_component_totals(db, owner_id)
        if before_totals != report["current"]:
            raise ConversionConflict("Current owner totals do not match the approved report")

        ids = json.loads(approval.approved_source_ids)
        sources = {row["source"]["id"]: row for row in report["sources"]}
        deps = report["dependencies"]
        containers = {row["id"]: row for row in deps["investment_accounts"]}
        portfolios = {row["id"]: row for row in deps["portfolios"]}
        accounts = {row["id"]: row for row in deps["accounts"]}
        instruments = {row["id"]: row for row in deps["instruments"]}
        specs = {row["id"]: row for row in deps["instrument_specifications"]}
        _validate_account_groups(report, ids, containers)
        correction_map = json.loads(approval.account_corrections_cents)
        before_state = {}
        created_openings = []
        created_entries = []
        for source_id in ids:
            row = sources[source_id]
            mapping = row["mapping"]
            source_snapshot = row["source"]
            container = containers[mapping["investment_account_id"]]
            account_id = container["account_id"]
            instrument = instruments[mapping["instrument_id"]]
            spec = specs[mapping["specification_id"]]
            for table_rows, target_id, label in (
                (accounts, account_id, "account"), (portfolios, container["portfolio_id"], "portfolio"),
            ):
                if not table_rows[target_id]["active"]:
                    raise ConversionConflict(f"Approved {label} is no longer active")
            if not container["active"] or not instrument["active"]:
                raise ConversionConflict("Approved conversion target is no longer active")
            if db.execute(select(OpeningPosition.id).where(
                OpeningPosition.owner_id == owner_id,
                OpeningPosition.source_investment_id == source_id,
            )).first():
                raise ConversionConflict("Source already has conversion history")
            spec_obj = db.execute(select(InstrumentSpecification).where(
                InstrumentSpecification.owner_id == owner_id,
                InstrumentSpecification.instrument_id == mapping["instrument_id"],
                InstrumentSpecification.id == mapping["specification_id"],
            )).scalar_one()
            existing_instrument = db.execute(select(Instrument).where(
                Instrument.owner_id == owner_id, Instrument.id == mapping["instrument_id"]
            )).scalar_one()
            source_obj = db.execute(select(Investment).where(
                Investment.owner_id == owner_id, Investment.id == source_id
            )).scalar_one()
            if not source_obj.active:
                raise ConversionConflict("Inactive source cannot be converted")
            position = OpeningPosition(
                owner_id=owner_id, approval_id=approval.id, source_investment_id=source_id,
                portfolio_id=container["portfolio_id"], investment_account_id=container["id"],
                cash_account_id=account_id, instrument_id=existing_instrument.id,
                specification_id=spec_obj.id, specification_version=spec_obj.version,
                quantity_units=source_obj.quantity_units,
                entered_basis_cents=None if row["basis_status"] == "unknown" else source_obj.cost_basis_cents,
                basis_status=row["basis_status"],
                reviewed_zero_basis_evidence=(
                    "Explicit zero-basis review recorded in approved report"
                    if source_obj.cost_basis_cents == 0 and mapping.get("zero_basis_reviewed")
                    else None
                ),
                original_entered_value_cents=source_obj.current_value_cents,
                valuation_provenance=row["valuation"]["provenance"],
                valuation_evidence=row["valuation"].get("evidence"),
                valuation_as_of_date=(datetime.fromisoformat(row["valuation"]["as_of"]).date()
                                      if row["valuation"].get("as_of") else None),
                source_edited_at=(datetime.fromisoformat(source_snapshot["updated_at"])
                                  if source_snapshot.get("updated_at") else None),
                acquisition_date=None, source_snapshot=json.dumps(source_snapshot, sort_keys=True),
                status="active",
            )
            db.add(position)
            db.flush()
            eligibility = ValuationEligibility(
                owner_id=owner_id, source_investment_id=source_id, opening_position_id=position.id,
                approval_id=approval.id, representation="opening", status="active",
            )
            db.add(eligibility)
            created_openings.append(position.id)
            before_state[str(account_id)] = {
                "before_cents": _account_balance(db, owner_id, account_id),
                "correction_cents": correction_map[str(account_id)],
            }

        for account_key, correction in correction_map.items():
            account_id = int(account_key)
            before = _account_balance(db, owner_id, account_id)
            before_state[str(account_id)]["before_cents"] = before
            if correction:
                entry = CashReconciliationEntry(
                    owner_id=owner_id, approval_id=approval.id, account_id=account_id,
                    delta_cents=correction, reason="combined_balance_overlap",
                    evidence=f"Approved reconciliation report {approval.report_sha256}",
                    before_balance_cents=before, after_balance_cents=before + correction,
                    actor_id=actor_id,
                )
                db.add(entry)
                db.flush()
                created_entries.append(entry.id)
            before_state[str(account_id)]["after_cents"] = before + correction

        db.flush()
        _after_conversion_ledger_writes()
        after_totals = _compute_component_totals(db, owner_id)
        if after_totals != report["proposed"]:
            raise ConversionConflict("Reader totals do not match the approved component totals")
        measured_delta = after_totals["net_worth_cents"] - before_totals["net_worth_cents"]
        if (measured_delta != report["delta_cents"]
                or measured_delta != int(approval.expected_delta_cents)):
            raise ConversionConflict("Measured net-worth delta does not match the approved delta")

        approval.execution_idempotency_key = data.idempotency_key
        approval.execution_payload_sha256 = payload_hash
        approval.executed_at = utc_now()
        approval.state = "executed"
        event = ConversionEvent(
            owner_id=owner_id, approval_id=approval.id, event_kind="executed",
            before_totals=json.dumps(before_totals, sort_keys=True),
            after_totals=json.dumps(after_totals, sort_keys=True),
            source_account_state=json.dumps({
                "accounts": before_state,
                "post_dependencies": _reversal_dependencies(db, owner_id),
            }, sort_keys=True),
            cutoff=utc_now(), actor_id=actor_id, report_sha256=approval.report_sha256,
            backup_evidence_reference=approval.backup_evidence_reference,
            linked_ids=json.dumps({"opening_position_ids": created_openings,
                                   "cash_entry_ids": created_entries, "source_ids": ids}),
        )
        db.add(event)
        db.flush()
        result = _event_result(event)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise ConversionConflict("Conversion conflicts with existing history") from exc
    except Exception:
        db.rollback()
        raise


def _event_result(event):
    return {
        "event_id": event.id, "approval_id": event.approval_id, "event_kind": event.event_kind,
        "before_totals": json.loads(event.before_totals),
        "after_totals": json.loads(event.after_totals),
        "linked_ids": json.loads(event.linked_ids),
        "source_account_state": json.loads(event.source_account_state),
        "cutoff": _aware(event.cutoff).isoformat(),
        "created_at": _aware(event.created_at).isoformat(),
        "actor_id": event.actor_id,
    }


def get_evidence(db: Session, owner_id: str, approval_id: int) -> dict:
    _lock_owner(db, require_owner_id(owner_id))
    approval = _approval(db, require_owner_id(owner_id), approval_id)
    event_rows = db.execute(select(ConversionEvent).where(
        ConversionEvent.owner_id == owner_id, ConversionEvent.approval_id == approval_id,
    ).order_by(ConversionEvent.id)).scalars().all()
    openings = db.execute(select(OpeningPosition).where(
        OpeningPosition.owner_id == owner_id, OpeningPosition.approval_id == approval_id,
    ).order_by(OpeningPosition.id)).scalars().all()
    eligibility = db.execute(select(ValuationEligibility).where(
        ValuationEligibility.owner_id == owner_id, ValuationEligibility.approval_id == approval_id,
    ).order_by(ValuationEligibility.id)).scalars().all()
    entries = db.execute(select(CashReconciliationEntry).where(
        CashReconciliationEntry.owner_id == owner_id, CashReconciliationEntry.approval_id == approval_id,
    ).order_by(CashReconciliationEntry.id)).scalars().all()
    return {
        "approval": {
            "id": approval.id, "state": approval.state, "report_sha256": approval.report_sha256,
            "report_format_version": approval.report_format_version,
            "algorithm_version": approval.algorithm_version,
            "approved_at": _aware(approval.approved_at).isoformat(),
            "executed_at": _aware(approval.executed_at).isoformat() if approval.executed_at else None,
            "reversed_at": _aware(approval.reversed_at).isoformat() if approval.reversed_at else None,
            "rollback_deadline": _aware(approval.rollback_deadline).isoformat(),
            "backup_evidence_reference": approval.backup_evidence_reference,
            "backup_cutoff": _aware(approval.backup_cutoff).isoformat(),
            "warnings": json.loads(approval.canonical_report).get("warnings", []),
        },
        "report": json.loads(approval.canonical_report),
        "opening_positions": [_evidence_row(p) | {
            "source_snapshot": json.loads(p.source_snapshot),
        } for p in openings],
        "eligibility": [_evidence_row(e) for e in eligibility],
        "cash_entries": [_evidence_row(e) for e in entries],
        "events": [_event_result(e) | {"reason": e.reason} for e in event_rows],
    }


def _evidence_row(row):
    return {
        column.name: _aware(value).isoformat() if isinstance(value, datetime)
        else value.isoformat() if hasattr(value, "isoformat") else value
        for column in row.__table__.columns
        for value in (getattr(row, column.name),)
    }


def review_context(db: Session, owner_id: str) -> dict:
    """Owner-private history for explicit later-batch declarations, never approval."""
    owner_id = require_owner_id(owner_id)
    lock_owner_financial_writes(db, owner_id)
    try:
        state = reconciliation_service._conversion_snapshot(db, owner_id)
        account_ids = sorted({
            row["cash_account_id"] for row in state["opening_positions"]
            if row["cash_account_id"] is not None
        } | {row["account_id"] for row in state["cash_reconciliation_entries"]})
        return {"accounts": [{
            "account_id": account_id,
            **reconciliation_service.account_conversion_history(state, account_id),
        } for account_id in account_ids]}
    finally:
        db.rollback()


def reverse(db: Session, owner_id: str, actor_id: str, approval_id: int, reason: str) -> dict:
    owner_id = require_owner_id(owner_id)
    _lock_owner(db, owner_id)
    try:
        approval = _approval(db, owner_id, approval_id)
        prior = db.execute(select(ConversionEvent).where(
            ConversionEvent.owner_id == owner_id, ConversionEvent.approval_id == approval_id,
            ConversionEvent.event_kind == "reversed",
        )).scalar_one_or_none()
        if prior:
            if prior.reason != reason:
                raise ConversionConflict("Conversion was reversed with a different confirmed reason")
            result = _event_result(prior)
            db.commit()
            return result
        if approval.state != "executed":
            raise ConversionConflict("Only an executed conversion can be reversed")
        if _aware(utc_now()) > _aware(approval.rollback_deadline):
            raise ConversionConflict("Approved reversal window has expired")
        _backup_gate(db, os.getenv("SERENITY_CONVERSION_TEST_MODE") == "1",
                     approval.backup_evidence_reference, approval.backup_cutoff,
                     approval.rollback_deadline)
        executed = db.execute(select(ConversionEvent).where(
            ConversionEvent.owner_id == owner_id, ConversionEvent.approval_id == approval_id,
            ConversionEvent.event_kind == "executed",
        )).scalar_one()
        later_events = list(db.scalars(select(ConversionEvent.id).where(
            ConversionEvent.owner_id == owner_id,
            ConversionEvent.id > executed.id,
        ).order_by(ConversionEvent.id)))
        if later_events:
            raise ConversionConflict(
                f"Later conversion activity blocks reversal; conversion event IDs: {later_events}"
            )
        committed_state = json.loads(executed.source_account_state)
        baseline = committed_state.get("post_dependencies")
        if not baseline:
            raise ConversionConflict("Verified post-conversion baseline is unavailable")
        current_dependencies = _reversal_dependencies(db, owner_id)
        if reconciliation_service._fingerprint(current_dependencies) != reconciliation_service._fingerprint(baseline):
            blockers = _blocking_references(baseline, current_dependencies)
            raise ConversionConflict(
                "Post-conversion dependencies changed; reversal is unsafe; "
                f"blocking references: {json.dumps(blockers, sort_keys=True)}"
            )
        before_totals = _compute_component_totals(db, owner_id)
        if before_totals != json.loads(executed.after_totals):
            raise ConversionConflict("Current component totals changed after conversion")
        state = committed_state["accounts"]
        for account_key, balances in state.items():
            if _account_balance(db, owner_id, int(account_key)) != balances["after_cents"]:
                raise ConversionConflict("Corrected account balance changed; reversal is unsafe")
        openings = db.execute(select(OpeningPosition).where(
            OpeningPosition.owner_id == owner_id, OpeningPosition.approval_id == approval_id,
        )).scalars().all()
        entries = db.execute(select(CashReconciliationEntry).where(
            CashReconciliationEntry.owner_id == owner_id,
            CashReconciliationEntry.approval_id == approval_id,
            CashReconciliationEntry.reason == "combined_balance_overlap",
        )).scalars().all()
        reversed_entries = []
        for entry in entries:
            current_balance = _account_balance(db, owner_id, entry.account_id)
            compensation = CashReconciliationEntry(
                owner_id=owner_id, approval_id=approval.id, account_id=entry.account_id,
                delta_cents=-entry.delta_cents, reason="conversion_reversal",
                evidence=reason, before_balance_cents=current_balance,
                after_balance_cents=current_balance - entry.delta_cents,
                original_entry_id=entry.id, actor_id=actor_id,
            )
            db.add(compensation)
            db.flush()
            reversed_entries.append(compensation.id)
        opening_ids = {p.id for p in openings}
        eligibility = db.execute(select(ValuationEligibility).where(
            ValuationEligibility.owner_id == owner_id,
            ValuationEligibility.approval_id == approval_id,
        )).scalars().all()
        if (len(eligibility) != len(openings)
                or any(position.status != "active" for position in openings)
                or any(row.status != "active" or row.representation != "opening"
                       for row in eligibility)):
            raise ConversionConflict("Opening eligibility changed; reversal is unsafe")
        for position in openings:
            position.status = "reversed"
        for row in eligibility:
            row.representation = "legacy"
            row.status = "reversed"
        approval.state = "reversed"
        approval.reversed_at = utc_now()
        db.flush()
        after_totals = _compute_component_totals(db, owner_id)
        if after_totals != json.loads(executed.before_totals):
            raise ConversionConflict("Reversal totals do not restore the approved components")
        event = ConversionEvent(
            owner_id=owner_id, approval_id=approval.id, event_kind="reversed",
            before_totals=json.dumps(before_totals, sort_keys=True),
            after_totals=json.dumps(after_totals, sort_keys=True),
            source_account_state=json.dumps(state, sort_keys=True), cutoff=utc_now(),
            actor_id=actor_id, report_sha256=approval.report_sha256,
            backup_evidence_reference=approval.backup_evidence_reference,
            linked_ids=json.dumps({"opening_position_ids": sorted(opening_ids),
                                   "compensating_cash_entry_ids": reversed_entries}),
            reason=reason,
        )
        db.add(event)
        db.flush()
        result = _event_result(event)
        db.commit()
        return result
    except IntegrityError as exc:
        db.rollback()
        raise ConversionConflict("Conversion reversal conflicts with later history") from exc
    except Exception:
        db.rollback()
        raise