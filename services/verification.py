"""Owner declarations bound to current facts; edits never manufacture evidence."""

from datetime import datetime, timedelta, timezone
import hashlib
import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from models.account import utc_now
from models.verification import Verification
from schemas.verification import VerificationCreate
from services import account_service, portfolio_service
from services.ownership import require_owner_id
from utils.money import cents_to_dollars

INTERVAL = timedelta(days=30)


def utc(value):
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def saved_rows(db, owner_id):
    return list(db.scalars(select(Verification).where(
        Verification.owner_id == require_owner_id(owner_id)
    ).order_by(Verification.id)))


def evidence_read(row):
    return {
        "id": row.id, "kind": row.kind, "target_id": row.target_id,
        "as_of": row.as_of.isoformat(), "evidence": row.evidence,
        "recorded_at": utc(row.recorded_at).isoformat(),
    }


def evidence_status(row, snapshot, now):
    if row is None:
        return "UNKNOWN"
    # Revalidate persisted evidence; neither corruption nor a future date is proof.
    VerificationCreate(as_of=row.as_of, evidence=row.evidence, snapshot=row.snapshot)
    if row.as_of > now.date() or utc(row.recorded_at) > now:
        raise ValueError("Future evidence")
    if row.snapshot != snapshot:
        return "CHANGED"
    return "STALE" if (now.date() - row.as_of).days >= INTERVAL.days else "VERIFIED"


def target(db, owner_id, kind, row):
    """Fingerprint the fact and source generation, excluding names/notes/edits.

    A digest is a comparison token, not approval or a secret. Reads are momentary
    observations, not serializable financial transactions.
    """
    if kind == "account_balance":
        cents = account_service.calculate_current_balance_cents(row, db)
        identity = [row.account_type, row.classification, row.institution]
        generation = row.created_at
    elif kind == "debt_balance":
        cents = row.balance_cents
        identity = [row.debt_type]
        generation = row.created_at
    elif kind == "legacy_valuation":
        cents = row.current_value_cents
        identity = [row.ticker, row.quantity_units, row.portfolio_id, row.investment_account_id]
        generation = row.created_at
    else:
        cents = row.original_entered_value_cents
        identity = [
            row.source_investment_id, row.instrument_id, row.specification_id,
            row.quantity_units, row.approval_id,
        ]
        generation = row.captured_at
    if generation is None:
        raise ValueError("Missing source generation")
    material = [owner_id, kind, row.id, utc(generation).isoformat(), cents, identity]
    digest = hashlib.sha256(json.dumps(material, separators=(",", ":")).encode()).hexdigest()
    return {
        "kind": kind, "target_id": row.id,
        "label": row.name if kind != "opening_valuation" else "Selected opening valuation",
        "amount": str(cents_to_dollars(cents)), "snapshot": digest,
    }


def domain_targets(db, owner_id, key, rows):
    active = [row for row in rows if row.active]
    if key == "accounts":
        return [target(db, owner_id, "account_balance", r) for r in active]
    if key == "debts":
        return [target(db, owner_id, "debt_balance", r) for r in active]
    legacy = portfolio_service.eligible_legacy_investments(db, owner_id, rows)
    _, openings = portfolio_service.selected_valuation_records(db, owner_id)
    return (
        [target(db, owner_id, "legacy_valuation", r) for r in legacy]
        + [target(db, owner_id, "opening_valuation", r) for r in openings]
    )


def current_targets(db, owner_id):
    # Reuse Data Health's canonical validation/selection; never accept corrupt facts.
    from services.data_health import _freshness, _load, _opening_freshness
    now = utc_now()
    targets = []
    for key in ("accounts", "debts", "investments"):
        rows = _load(db, owner_id, key)
        active = [r for r in rows if r.active]
        if key == "investments":
            active = portfolio_service.eligible_legacy_investments(db, owner_id, rows)
            _, openings = portfolio_service.selected_valuation_records(db, owner_id)
            _opening_freshness(openings, now)
        # Date validation is shared with the redacted summary; its reminders
        # are not evidence and do not manufacture a check in this review API.
        _freshness(active, now)
        targets.extend(domain_targets(db, owner_id, key, rows))
    return targets


def review(db, owner_id, *, now=None):
    owner_id = require_owner_id(owner_id)
    now = now or utc_now()
    saved = {(r.kind, r.target_id): r for r in saved_rows(db, owner_id)}
    targets = current_targets(db, owner_id)
    for t in targets:
        row = saved.pop((t["kind"], t["target_id"]), None)
        try:
            t["status"] = evidence_status(row, t["snapshot"], now)
            t["verification"] = evidence_read(row) if row else None
        except (ValueError, TypeError, AttributeError):
            t["status"] = "INCONSISTENT"
            t["verification"] = evidence_read(row) if row else None
    # Removed or no-longer-selected sources do not establish any current fact.
    return {
        "checked_at": now.isoformat(), "targets": targets,
        "retained": [evidence_read(r) for r in saved.values()],
    }


def save(db, owner_id, kind, target_id, payload):
    owner_id = require_owner_id(owner_id)
    current = next((t for t in current_targets(db, owner_id)
                    if t["kind"] == kind and t["target_id"] == target_id), None)
    if current is None:
        raise HTTPException(404, "Reviewable record not found")
    if current["snapshot"] != payload.snapshot:
        raise HTTPException(409, "The financial snapshot changed. Reload and check it again.")
    row = db.scalar(select(Verification).where(
        Verification.owner_id == owner_id, Verification.kind == kind,
        Verification.target_id == target_id,
    ))
    if row is None:
        row = Verification(owner_id=owner_id, kind=kind, target_id=target_id)
        db.add(row)
    row.snapshot = payload.snapshot
    row.as_of = payload.as_of
    row.evidence = payload.evidence
    row.recorded_at = utc_now()
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "Another check was saved. Reload before replacing it.") from None
    return evidence_read(row)


def remove(db, owner_id, evidence_id):
    row = db.scalar(select(Verification).where(
        Verification.owner_id == require_owner_id(owner_id),
        Verification.id == evidence_id,
    ))
    if row is None:
        raise HTTPException(404, "Evidence not found")
    db.delete(row)
    db.commit()