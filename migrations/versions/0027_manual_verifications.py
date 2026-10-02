"""Latest owner-only manual verification evidence; financial rows unchanged."""

from alembic import context, op
import sqlalchemy as sa

revision = "0027_manual_verifications"
down_revision = "0026_system_observations"
branch_labels = None
depends_on = None


def upgrade():
    # Polymorphic source references deliberately survive source deletion.
    # Source resolution always checks owner and snapshot generation in services.
    op.create_table(
        "manual_verifications",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("owner_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.String(64), nullable=False),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "kind", "target_id", name="uq_manual_verifications_target"),
        sa.CheckConstraint(
            "kind IN ('account_balance', 'debt_balance', 'legacy_valuation', 'opening_valuation')",
            name="ck_manual_verifications_kind",
        ),
        sa.CheckConstraint("target_id > 0", name="ck_manual_verifications_target"),
        sa.CheckConstraint("length(trim(evidence)) BETWEEN 1 AND 1000", name="ck_manual_verifications_evidence"),
        sa.CheckConstraint("length(snapshot) = 64", name="ck_manual_verifications_snapshot"),
    )


def downgrade():
    if context.is_offline_mode():
        raise RuntimeError("Evidence downgrade requires an online preservation check")
    connection = op.get_bind()
    if connection.dialect.name == "postgresql":
        connection.execute(sa.text("LOCK TABLE manual_verifications IN ACCESS EXCLUSIVE MODE"))
    if connection.scalar(sa.text("SELECT COUNT(*) FROM manual_verifications")):
        raise RuntimeError("Cannot downgrade while manual verification evidence exists")
    op.drop_table("manual_verifications")