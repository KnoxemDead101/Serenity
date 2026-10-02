"""Repair the approval delta type and install conversion write guards."""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from migrations.conversion_write_guards import downgrade_guards, upgrade_guards

revision: str = "0017_conversion_guards"
down_revision: Union[str, None] = "0016_approved_conversions"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

CONVERSION_TABLES = (
    "reconciliation_approvals",
    "opening_positions",
    "valuation_eligibility",
    "cash_reconciliation_entries",
    "conversion_events",
)

APPROVAL_TRIGGERS = {
    "trg_reconciliation_approvals_no_delete",
    "trg_reconciliation_approvals_immutable_content",
}


def _approval_triggers(connection) -> list[str]:
    triggers = connection.execute(sa.text(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'trigger' AND tbl_name = 'reconciliation_approvals'"
    )).all()
    definitions = {name: definition for name, definition in triggers}
    missing = APPROVAL_TRIGGERS - definitions.keys()
    if missing:
        raise RuntimeError(
            "Cannot correct 0016 approval delta type: missing immutable approval "
            f"triggers: {', '.join(sorted(missing))}"
        )
    return list(definitions.values())


def _require_empty_conversion_ledger(connection) -> None:
    for table in CONVERSION_TABLES:
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                f"Cannot correct 0016 approval delta type: {table} contains "
                "conversion history; retain history without altering it"
            )


def upgrade() -> None:
    connection = op.get_bind()
    column = next(
        column for column in sa.inspect(connection).get_columns("reconciliation_approvals")
        if column["name"] == "expected_delta_cents"
    )
    existing_type = column["type"].compile(dialect=connection.dialect).upper()

    # Fresh installs already get BIGINT from canonical revision 0016. Older
    # installs may have applied 0016 while this scalar was still TEXT.
    if existing_type == "TEXT":
        # Do all safety checks before changing the schema. A TEXT scalar could
        # be converted only on a completely empty conversion ledger.
        _require_empty_conversion_ledger(connection)

        if connection.dialect.name == "sqlite":
            trigger_definitions = _approval_triggers(connection)
            with op.batch_alter_table("reconciliation_approvals") as batch:
                batch.alter_column(
                    "expected_delta_cents",
                    existing_type=sa.Text(),
                    type_=sa.BigInteger(),
                    existing_nullable=False,
                )
            # SQLite batch recreation drops table triggers; restore their exact
            # definitions so the approval evidence protections remain in force.
            for definition in trigger_definitions:
                op.execute(definition)
        elif connection.dialect.name == "postgresql":
            op.alter_column(
                "reconciliation_approvals",
                "expected_delta_cents",
                existing_type=sa.Text(),
                type_=sa.BigInteger(),
                existing_nullable=False,
                postgresql_using="expected_delta_cents::BIGINT",
            )
        else:
            raise RuntimeError(
                "Cannot correct 0016 approval delta type on unsupported database "
                f"dialect {connection.dialect.name}"
            )
    elif existing_type != "BIGINT":
        raise RuntimeError(
            "Cannot correct 0016 approval delta type: expected BIGINT or legacy "
            f"TEXT, found {existing_type}"
        )

    # This runs on both legacy and canonical 0016 layouts.
    upgrade_guards()


def downgrade() -> None:
    # Never narrow the canonical 0016 BIGINT field or remove conversion data.
    connection = op.get_bind()
    for table in CONVERSION_TABLES:
        if connection.execute(sa.text(f"SELECT 1 FROM {table} LIMIT 1")).first():
            raise RuntimeError(
                "Cannot downgrade conversion guards while conversion history "
                f"exists in {table}; retain the schema and audit protections"
            )
    downgrade_guards()