"""Migrated conversion audit guards retain synthetic approval/event evidence."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session
from sqlalchemy.engine import URL

from models.conversion import ConversionEvent, ReconciliationApproval
from scripts import rehearse_database_restore as rehearsal


def test_migrated_schema_rejects_mutation_and_deletion_of_audit_evidence(tmp_path):
    database = tmp_path / "migrated-conversion-ledger.db"
    url = URL.create("sqlite", database=str(database)).render_as_string()
    rehearsal.migrate_source(url)
    engine = create_engine(url)
    now = datetime.now(timezone.utc)

    try:
        with Session(engine) as db:
            approval = ReconciliationApproval(
                owner_id="synthetic-owner",
                canonical_report=b'{"fixture":"migrated-audit-guard"}',
                report_format_version=2,
                algorithm_version="test",
                report_sha256="a" * 64,
                signed_token_evidence="synthetic test evidence",
                preview_cutoff=now,
                source_fingerprint="synthetic fingerprint",
                approving_actor_id="synthetic-actor",
                approved_at=now,
                approved_source_ids="[]",
                account_corrections_cents="{}",
                before_component_totals_cents="{}",
                after_component_totals_cents="{}",
                expected_delta_cents="0",
                backup_evidence_reference="synthetic://test",
                backup_cutoff=now,
                rollback_deadline=now,
            )
            db.add(approval)
            db.flush()
            event = ConversionEvent(
                owner_id="synthetic-owner",
                approval_id=approval.id,
                event_kind="failed",
                before_totals="{}",
                after_totals="{}",
                source_account_state="{}",
                cutoff=now,
                actor_id="synthetic-actor",
                report_sha256="a" * 64,
                backup_evidence_reference="synthetic://test",
                linked_ids="{}",
                reason="synthetic test fixture",
            )
            db.add(event)
            db.commit()
            approval_id, event_id = approval.id, event.id

        # These assertions use Alembic's installed SQLite triggers, not
        # metadata.create_all(), which intentionally does not install them.
        for statement, values in (
            ("UPDATE reconciliation_approvals SET canonical_report = :value WHERE id = :id",
             {"value": b'{"tampered":true}', "id": approval_id}),
            ("DELETE FROM reconciliation_approvals WHERE id = :id", {"id": approval_id}),
            ("UPDATE conversion_events SET reason = :value WHERE id = :id",
             {"value": "tampered", "id": event_id}),
            ("DELETE FROM conversion_events WHERE id = :id", {"id": event_id}),
        ):
            with pytest.raises(DBAPIError):
                with engine.begin() as connection:
                    connection.execute(text(statement), values)

        with Session(engine) as db:
            assert db.get(ReconciliationApproval, approval_id).canonical_report == (
                b'{"fixture":"migrated-audit-guard"}'
            )
            assert db.get(ConversionEvent, event_id).reason == "synthetic test fixture"
    finally:
        engine.dispose()