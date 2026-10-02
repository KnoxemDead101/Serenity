"""Add the empty approved-conversion ledger without changing financial rows."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0016_approved_conversions"
down_revision: Union[str, None] = "0015_portfolio_containers"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _create_sqlite_guards() -> None:
    # SQLite has no per-table permissions/triggers for row fields. These guards
    # preserve immutable evidence while still allowing lifecycle state changes.
    op.execute("""
        CREATE TRIGGER trg_reconciliation_approvals_no_delete
        BEFORE DELETE ON reconciliation_approvals
        BEGIN SELECT RAISE(ABORT, 'reconciliation approvals are retained audit evidence'); END
    """)
    approval_fields = (
        "owner_id", "canonical_report", "report_format_version", "algorithm_version",
        "report_sha256", "signed_token_evidence", "preview_cutoff", "source_fingerprint",
        "approving_actor_id", "approved_at", "approved_source_ids",
        "account_corrections_cents", "before_component_totals_cents",
        "after_component_totals_cents", "expected_delta_cents",
        "backup_evidence_reference", "backup_cutoff", "rollback_deadline",
    )
    changed = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in approval_fields)
    changed += (
        " OR (OLD.execution_idempotency_key IS NOT NULL AND "
        "NEW.execution_idempotency_key IS NOT OLD.execution_idempotency_key)"
        " OR (OLD.execution_payload_sha256 IS NOT NULL AND "
        "NEW.execution_payload_sha256 IS NOT OLD.execution_payload_sha256)"
        " OR (OLD.state != 'approved' AND ("
        "NEW.execution_idempotency_key IS NOT OLD.execution_idempotency_key OR "
        "NEW.execution_payload_sha256 IS NOT OLD.execution_payload_sha256))"
    )
    op.execute(f"""
        CREATE TRIGGER trg_reconciliation_approvals_immutable_content
        BEFORE UPDATE ON reconciliation_approvals
        WHEN {changed}
        BEGIN SELECT RAISE(ABORT, 'approved report content is immutable'); END
    """)
    opening_fields = (
        "owner_id", "approval_id", "source_investment_id", "portfolio_id",
        "investment_account_id", "cash_account_id", "instrument_id", "specification_id",
        "specification_version", "quantity_units", "entered_basis_cents", "basis_status",
        "reviewed_zero_basis_evidence", "original_entered_value_cents",
        "valuation_provenance", "valuation_evidence", "valuation_as_of_date",
        "captured_at", "source_edited_at", "acquisition_date", "source_snapshot",
    )
    changed = " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in opening_fields)
    op.execute(f"""
        CREATE TRIGGER trg_opening_positions_immutable_snapshot
        BEFORE UPDATE ON opening_positions
        WHEN {changed}
        BEGIN SELECT RAISE(ABORT, 'opening position snapshot is immutable'); END
    """)
    op.execute("""
        CREATE TRIGGER trg_opening_positions_no_delete
        BEFORE DELETE ON opening_positions
        BEGIN SELECT RAISE(ABORT, 'opening positions are retained audit evidence'); END
    """)
    for table in ("cash_reconciliation_entries", "conversion_events"):
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER trg_{table}_no_{operation.lower()}
                BEFORE {operation} ON {table}
                BEGIN SELECT RAISE(ABORT, '{table} are append-only audit evidence'); END
            """)
    op.execute("""
        CREATE TRIGGER trg_valuation_eligibility_no_delete
        BEFORE DELETE ON valuation_eligibility
        BEGIN SELECT RAISE(ABORT, 'valuation eligibility history is retained'); END
    """)


def _create_postgresql_guards() -> None:
    op.execute("""
        CREATE FUNCTION conversion_append_only_guard() RETURNS trigger AS $$
        BEGIN
            RAISE EXCEPTION '% is append-only audit evidence', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
    """)
    for table in ("cash_reconciliation_entries", "conversion_events"):
        op.execute(f"""
            CREATE TRIGGER trg_{table}_append_only
            BEFORE UPDATE OR DELETE ON {table}
            FOR EACH ROW EXECUTE FUNCTION conversion_append_only_guard()
        """)
    op.execute("""
        CREATE FUNCTION conversion_approval_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'reconciliation approvals are retained audit evidence';
            END IF;
            IF ROW(
                NEW.owner_id, NEW.canonical_report, NEW.report_format_version,
                NEW.algorithm_version, NEW.report_sha256, NEW.signed_token_evidence,
                NEW.preview_cutoff, NEW.source_fingerprint, NEW.approving_actor_id,
                NEW.approved_at, NEW.approved_source_ids, NEW.account_corrections_cents,
                NEW.before_component_totals_cents, NEW.after_component_totals_cents,
                NEW.expected_delta_cents, NEW.backup_evidence_reference,
                NEW.backup_cutoff, NEW.rollback_deadline
            ) IS DISTINCT FROM ROW(
                OLD.owner_id, OLD.canonical_report, OLD.report_format_version,
                OLD.algorithm_version, OLD.report_sha256, OLD.signed_token_evidence,
                OLD.preview_cutoff, OLD.source_fingerprint, OLD.approving_actor_id,
                OLD.approved_at, OLD.approved_source_ids, OLD.account_corrections_cents,
                OLD.before_component_totals_cents, OLD.after_component_totals_cents,
                OLD.expected_delta_cents, OLD.backup_evidence_reference,
                OLD.backup_cutoff, OLD.rollback_deadline
            ) THEN
                RAISE EXCEPTION 'approved report content is immutable';
            END IF;
            IF (OLD.execution_idempotency_key IS NOT NULL AND
                NEW.execution_idempotency_key IS DISTINCT FROM OLD.execution_idempotency_key) OR
               (OLD.execution_payload_sha256 IS NOT NULL AND
                NEW.execution_payload_sha256 IS DISTINCT FROM OLD.execution_payload_sha256) OR
               (OLD.state <> 'approved' AND
                ROW(NEW.execution_idempotency_key, NEW.execution_payload_sha256) IS DISTINCT FROM
                ROW(OLD.execution_idempotency_key, OLD.execution_payload_sha256)) THEN
                RAISE EXCEPTION 'execution idempotency binding is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_reconciliation_approvals_guard
        BEFORE UPDATE OR DELETE ON reconciliation_approvals
        FOR EACH ROW EXECUTE FUNCTION conversion_approval_guard()
    """)
    op.execute("""
        CREATE FUNCTION conversion_opening_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'opening positions are retained audit evidence';
            END IF;
            IF ROW(
                NEW.owner_id, NEW.approval_id, NEW.source_investment_id,
                NEW.portfolio_id, NEW.investment_account_id, NEW.cash_account_id,
                NEW.instrument_id, NEW.specification_id, NEW.specification_version,
                NEW.quantity_units, NEW.entered_basis_cents, NEW.basis_status,
                NEW.reviewed_zero_basis_evidence, NEW.original_entered_value_cents,
                NEW.valuation_provenance, NEW.valuation_evidence,
                NEW.valuation_as_of_date, NEW.captured_at, NEW.source_edited_at,
                NEW.acquisition_date, NEW.source_snapshot
            ) IS DISTINCT FROM ROW(
                OLD.owner_id, OLD.approval_id, OLD.source_investment_id,
                OLD.portfolio_id, OLD.investment_account_id, OLD.cash_account_id,
                OLD.instrument_id, OLD.specification_id, OLD.specification_version,
                OLD.quantity_units, OLD.entered_basis_cents, OLD.basis_status,
                OLD.reviewed_zero_basis_evidence, OLD.original_entered_value_cents,
                OLD.valuation_provenance, OLD.valuation_evidence,
                OLD.valuation_as_of_date, OLD.captured_at, OLD.source_edited_at,
                OLD.acquisition_date, OLD.source_snapshot
            ) THEN
                RAISE EXCEPTION 'opening position snapshot is immutable';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_opening_positions_guard
        BEFORE UPDATE OR DELETE ON opening_positions
        FOR EACH ROW EXECUTE FUNCTION conversion_opening_guard()
    """)
    op.execute("""
        CREATE FUNCTION conversion_eligibility_guard() RETURNS trigger AS $$
        BEGIN
            IF TG_OP = 'DELETE' THEN
                RAISE EXCEPTION 'valuation eligibility history is retained';
            END IF;
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_valuation_eligibility_no_delete
        BEFORE DELETE ON valuation_eligibility
        FOR EACH ROW EXECUTE FUNCTION conversion_eligibility_guard()
    """)


def upgrade() -> None:
    # Composite owner references are supported by additive unique indexes;
    # existing parent records and their financial values remain untouched.
    op.create_index("ux_investments_owner_id_id", "investments", ["owner_id", "id"], unique=True)
    op.create_index("ux_investment_accounts_owner_id_id", "investment_accounts", ["owner_id", "id"], unique=True)
    op.create_index("ux_instruments_owner_id_id", "instruments", ["owner_id", "id"], unique=True)
    op.create_index(
        "ux_instrument_specifications_owner_instrument_id_id",
        "instrument_specifications",
        ["owner_id", "instrument_id", "id"],
        unique=True,
    )

    op.create_table(
        "reconciliation_approvals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("canonical_report", sa.LargeBinary(), nullable=False),
        sa.Column("report_format_version", sa.Integer(), nullable=False),
        sa.Column("algorithm_version", sa.String(100), nullable=False),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("signed_token_evidence", sa.Text(), nullable=False),
        sa.Column("preview_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_fingerprint", sa.Text(), nullable=False),
        sa.Column("approving_actor_id", sa.String(255), nullable=False),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("approved_source_ids", sa.Text(), nullable=False),
        sa.Column("account_corrections_cents", sa.Text(), nullable=False),
        sa.Column("before_component_totals_cents", sa.Text(), nullable=False),
        sa.Column("after_component_totals_cents", sa.Text(), nullable=False),
        sa.Column("expected_delta_cents", sa.BigInteger(), nullable=False),
        sa.Column("backup_evidence_reference", sa.Text(), nullable=False),
        sa.Column("backup_cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rollback_deadline", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="approved"),
        sa.Column("execution_idempotency_key", sa.String(255)),
        sa.Column("execution_payload_sha256", sa.String(64)),
        sa.Column("executed_at", sa.DateTime(timezone=True)),
        sa.Column("reversed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("owner_id", "id", name="uq_reconciliation_approvals_owner_id_id"),
        sa.UniqueConstraint("owner_id", "report_sha256", name="uq_reconciliation_approvals_owner_digest"),
        sa.CheckConstraint(
            "state IN ('approved', 'executed', 'reversed', 'expired')",
            name="ck_reconciliation_approvals_state",
        ),
        sa.CheckConstraint(
            "(execution_idempotency_key IS NULL AND execution_payload_sha256 IS NULL) OR "
            "(execution_idempotency_key IS NOT NULL AND execution_payload_sha256 IS NOT NULL)",
            name="ck_reconciliation_approvals_execution_binding",
        ),
        sa.UniqueConstraint(
            "owner_id", "execution_idempotency_key",
            name="uq_reconciliation_approvals_owner_idempotency_key",
        ),
    )
    op.create_index("ix_reconciliation_approvals_owner_state", "reconciliation_approvals", ["owner_id", "state"])
    op.create_index("ix_reconciliation_approvals_owner_approved_at", "reconciliation_approvals", ["owner_id", "approved_at"])

    op.create_table(
        "opening_positions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("source_investment_id", sa.Integer(), nullable=False),
        sa.Column("portfolio_id", sa.Integer()),
        sa.Column("investment_account_id", sa.Integer()),
        sa.Column("cash_account_id", sa.Integer()),
        sa.Column("instrument_id", sa.Integer(), nullable=False),
        sa.Column("specification_id", sa.Integer(), nullable=False),
        sa.Column("specification_version", sa.Integer(), nullable=False),
        sa.Column("quantity_units", sa.BigInteger(), nullable=False),
        sa.Column("entered_basis_cents", sa.BigInteger()),
        sa.Column("basis_status", sa.String(10), nullable=False),
        sa.Column("reviewed_zero_basis_evidence", sa.Text()),
        sa.Column("original_entered_value_cents", sa.BigInteger(), nullable=False),
        sa.Column("valuation_provenance", sa.String(20)),
        sa.Column("valuation_evidence", sa.Text()),
        sa.Column("valuation_as_of_date", sa.Date()),
        sa.Column("captured_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_edited_at", sa.DateTime(timezone=True)),
        sa.Column("acquisition_date", sa.Date()),
        sa.Column("source_snapshot", sa.Text(), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.ForeignKeyConstraint(
            ["owner_id", "approval_id"], ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_opening_positions_owner_approval", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "source_investment_id"], ["investments.owner_id", "investments.id"],
            name="fk_opening_positions_owner_source", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "portfolio_id"], ["portfolios.owner_id", "portfolios.id"],
            name="fk_opening_positions_owner_portfolio", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "investment_account_id"], ["investment_accounts.owner_id", "investment_accounts.id"],
            name="fk_opening_positions_owner_container", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "cash_account_id"], ["accounts.owner_id", "accounts.id"],
            name="fk_opening_positions_owner_account", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "instrument_id"], ["instruments.owner_id", "instruments.id"],
            name="fk_opening_positions_owner_instrument", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "instrument_id", "specification_id"],
            ["instrument_specifications.owner_id", "instrument_specifications.instrument_id", "instrument_specifications.id"],
            name="fk_opening_positions_owner_specification", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("owner_id", "source_investment_id", name="uq_opening_positions_owner_source"),
        sa.UniqueConstraint("owner_id", "id", name="uq_opening_positions_owner_id_id"),
        sa.UniqueConstraint(
            "owner_id", "source_investment_id", "id", "approval_id",
            name="uq_opening_positions_owner_source_id_approval",
        ),
        sa.CheckConstraint("quantity_units >= 0", name="ck_opening_positions_quantity_nonnegative"),
        sa.CheckConstraint("basis_status IN ('known', 'unknown', 'unverified')", name="ck_opening_positions_basis_status"),
        sa.CheckConstraint("status IN ('active', 'reversed')", name="ck_opening_positions_status"),
    )
    op.create_index("ix_opening_positions_owner_approval", "opening_positions", ["owner_id", "approval_id"])
    op.create_index("ix_opening_positions_owner_status", "opening_positions", ["owner_id", "status"])

    op.create_table(
        "valuation_eligibility",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("source_investment_id", sa.Integer(), nullable=False),
        sa.Column("opening_position_id", sa.Integer(), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("representation", sa.String(7), nullable=False),
        sa.Column("status", sa.String(8), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "source_investment_id"], ["investments.owner_id", "investments.id"],
            name="fk_valuation_eligibility_owner_source", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "opening_position_id"], ["opening_positions.owner_id", "opening_positions.id"],
            name="fk_valuation_eligibility_owner_opening", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "approval_id"], ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_valuation_eligibility_owner_approval", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "source_investment_id", "opening_position_id", "approval_id"],
            [
                "opening_positions.owner_id", "opening_positions.source_investment_id",
                "opening_positions.id", "opening_positions.approval_id",
            ],
            name="fk_valuation_eligibility_exact_opening", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("owner_id", "source_investment_id", name="uq_valuation_eligibility_owner_source"),
        sa.UniqueConstraint("owner_id", "opening_position_id", name="uq_valuation_eligibility_owner_opening"),
        sa.CheckConstraint("representation IN ('legacy', 'opening')", name="ck_valuation_eligibility_representation"),
        sa.CheckConstraint("status IN ('active', 'reversed')", name="ck_valuation_eligibility_status"),
        sa.CheckConstraint(
            "(status = 'active' AND representation = 'opening') OR "
            "(status = 'reversed' AND representation = 'legacy')",
            name="ck_valuation_eligibility_selected_representation",
        ),
    )
    op.create_index("ix_valuation_eligibility_owner_representation", "valuation_eligibility", ["owner_id", "representation", "status"])

    op.create_table(
        "cash_reconciliation_entries",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("delta_cents", sa.BigInteger(), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("before_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("after_balance_cents", sa.BigInteger(), nullable=False),
        sa.Column("original_entry_id", sa.Integer()),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["owner_id", "approval_id"], ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_cash_reconciliation_entries_owner_approval", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "account_id"], ["accounts.owner_id", "accounts.id"],
            name="fk_cash_reconciliation_entries_owner_account", ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["owner_id", "original_entry_id"], ["cash_reconciliation_entries.owner_id", "cash_reconciliation_entries.id"],
            name="fk_cash_reconciliation_entries_owner_original", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint(
            "approval_id", "account_id", "reason",
            name="uq_cash_reconciliation_entries_approval_account_reason",
        ),
        sa.UniqueConstraint("owner_id", "id", name="uq_cash_reconciliation_entries_owner_id_id"),
        sa.CheckConstraint(
            "reason IN ('combined_balance_overlap', 'conversion_reversal')",
            name="ck_cash_reconciliation_entries_reason",
        ),
        sa.CheckConstraint(
            "(reason = 'combined_balance_overlap' AND original_entry_id IS NULL) OR "
            "(reason = 'conversion_reversal' AND original_entry_id IS NOT NULL)",
            name="ck_cash_reconciliation_entries_reversal_link",
        ),
    )
    op.create_index("ix_cash_reconciliation_entries_owner_account", "cash_reconciliation_entries", ["owner_id", "account_id"])
    op.create_index("ix_cash_reconciliation_entries_owner_approval", "cash_reconciliation_entries", ["owner_id", "approval_id"])

    op.create_table(
        "conversion_events",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(255), nullable=False),
        sa.Column("approval_id", sa.Integer(), nullable=False),
        sa.Column("event_kind", sa.String(8), nullable=False),
        sa.Column("before_totals", sa.Text(), nullable=False),
        sa.Column("after_totals", sa.Text(), nullable=False),
        sa.Column("source_account_state", sa.Text(), nullable=False),
        sa.Column("cutoff", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("report_sha256", sa.String(64), nullable=False),
        sa.Column("backup_evidence_reference", sa.Text(), nullable=False),
        sa.Column("linked_ids", sa.Text(), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.ForeignKeyConstraint(
            ["owner_id", "approval_id"], ["reconciliation_approvals.owner_id", "reconciliation_approvals.id"],
            name="fk_conversion_events_owner_approval", ondelete="RESTRICT",
        ),
        sa.UniqueConstraint("owner_id", "id", name="uq_conversion_events_owner_id_id"),
        sa.CheckConstraint("event_kind IN ('executed', 'reversed', 'failed')", name="ck_conversion_events_kind"),
    )
    op.create_index("ix_conversion_events_owner_approval", "conversion_events", ["owner_id", "approval_id"])
    op.create_index("ix_conversion_events_owner_created_at", "conversion_events", ["owner_id", "created_at"])
    op.create_index(
        "uq_conversion_events_owner_approval_executed",
        "conversion_events",
        ["owner_id", "approval_id"],
        unique=True,
        sqlite_where=sa.text("event_kind = 'executed'"),
        postgresql_where=sa.text("event_kind = 'executed'"),
    )
    op.create_index(
        "uq_conversion_events_owner_approval_reversed",
        "conversion_events",
        ["owner_id", "approval_id"],
        unique=True,
        sqlite_where=sa.text("event_kind = 'reversed'"),
        postgresql_where=sa.text("event_kind = 'reversed'"),
    )

    dialect = op.get_bind().dialect.name
    if dialect == "sqlite":
        _create_sqlite_guards()
    elif dialect == "postgresql":
        _create_postgresql_guards()


def downgrade() -> None:
    connection = op.get_bind()
    tables = (
        "conversion_events",
        "cash_reconciliation_entries",
        "valuation_eligibility",
        "opening_positions",
        "reconciliation_approvals",
    )
    for table in tables:
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                f"Cannot downgrade 0016: {table} contains conversion history; "
                "retain the migration or export and remove data intentionally"
            )

    dialect = connection.dialect.name
    if dialect == "postgresql":
        for table, function in (
            ("valuation_eligibility", "conversion_eligibility_guard"),
            ("opening_positions", "conversion_opening_guard"),
            ("reconciliation_approvals", "conversion_approval_guard"),
            ("conversion_events", "conversion_append_only_guard"),
            ("cash_reconciliation_entries", "conversion_append_only_guard"),
        ):
            op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_{'no_delete' if table == 'valuation_eligibility' else 'guard' if table in ('opening_positions', 'reconciliation_approvals') else 'append_only'} ON {table}")
        op.execute("DROP FUNCTION IF EXISTS conversion_eligibility_guard()")
        op.execute("DROP FUNCTION IF EXISTS conversion_opening_guard()")
        op.execute("DROP FUNCTION IF EXISTS conversion_approval_guard()")
        op.execute("DROP FUNCTION IF EXISTS conversion_append_only_guard()")
    elif dialect == "sqlite":
        for table in tables:
            names = connection.execute(
                sa.text("SELECT name FROM sqlite_master WHERE type='trigger' AND tbl_name=:table"),
                {"table": table},
            ).scalars()
            for name in names:
                op.execute(f'DROP TRIGGER IF EXISTS "{name}"')

    op.drop_index("uq_conversion_events_owner_approval_reversed", table_name="conversion_events")
    op.drop_index("uq_conversion_events_owner_approval_executed", table_name="conversion_events")
    op.drop_index("ix_conversion_events_owner_created_at", table_name="conversion_events")
    op.drop_index("ix_conversion_events_owner_approval", table_name="conversion_events")
    op.drop_table("conversion_events")
    op.drop_index("ix_cash_reconciliation_entries_owner_approval", table_name="cash_reconciliation_entries")
    op.drop_index("ix_cash_reconciliation_entries_owner_account", table_name="cash_reconciliation_entries")
    op.drop_table("cash_reconciliation_entries")
    op.drop_index("ix_valuation_eligibility_owner_representation", table_name="valuation_eligibility")
    op.drop_table("valuation_eligibility")
    op.drop_index("ix_opening_positions_owner_status", table_name="opening_positions")
    op.drop_index("ix_opening_positions_owner_approval", table_name="opening_positions")
    op.drop_table("opening_positions")
    op.drop_index("ix_reconciliation_approvals_owner_approved_at", table_name="reconciliation_approvals")
    op.drop_index("ix_reconciliation_approvals_owner_state", table_name="reconciliation_approvals")
    op.drop_table("reconciliation_approvals")
    op.drop_index("ux_instrument_specifications_owner_instrument_id_id", table_name="instrument_specifications")
    op.drop_index("ux_instruments_owner_id_id", table_name="instruments")
    op.drop_index("ux_investment_accounts_owner_id_id", table_name="investment_accounts")
    op.drop_index("ux_investments_owner_id_id", table_name="investments")