"""Database backstops for owner serialization and one-way audit transitions."""

from alembic import op


OWNER_TABLES = (
    "accounts", "bills", "businesses", "debts", "dependents", "income_profiles",
    "instruments", "instrument_specifications", "investments", "portfolios",
    "investment_accounts", "transactions", "transaction_corrections",
    "reconciliation_approvals", "opening_positions", "valuation_eligibility",
    "cash_reconciliation_entries", "conversion_events",
)


def upgrade_guards():
    dialect = op.get_bind().dialect.name
    if dialect == "postgresql":
        # Direct SQL writers join the same transaction-scoped protocol as the
        # services. Lock both owners in sorted order if ownership is changed.
        op.execute("""
            CREATE FUNCTION conversion_owner_write_lock() RETURNS trigger AS $$
            DECLARE previous_owner text; next_owner text; locked_owner text;
            BEGIN
                IF TG_OP != 'INSERT' THEN previous_owner := OLD.owner_id; END IF;
                IF TG_OP != 'DELETE' THEN next_owner := NEW.owner_id; END IF;
                FOR locked_owner IN
                    SELECT DISTINCT owner FROM unnest(
                        ARRAY[previous_owner, next_owner]
                    ) AS owner WHERE owner IS NOT NULL ORDER BY owner
                LOOP
                    PERFORM pg_advisory_xact_lock(hashtextextended(locked_owner, 0));
                END LOOP;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        for table in OWNER_TABLES:
            op.execute(f"""
                CREATE TRIGGER trg_conversion_owner_write
                BEFORE INSERT OR UPDATE OR DELETE ON {table}
                FOR EACH ROW EXECUTE FUNCTION conversion_owner_write_lock()
            """)
        op.execute("""
            CREATE FUNCTION conversion_source_read_only() RETURNS trigger AS $$
            BEGIN
                PERFORM pg_advisory_xact_lock(hashtextextended(OLD.owner_id, 0));
                IF EXISTS (
                    SELECT 1 FROM valuation_eligibility
                    WHERE owner_id = OLD.owner_id AND source_investment_id = OLD.id
                      AND representation = 'opening' AND status = 'active'
                ) THEN
                    RAISE EXCEPTION 'converted original investment is read-only';
                END IF;
                IF TG_OP = 'DELETE' THEN RETURN OLD; END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql
        """)
        op.execute("""
            CREATE TRIGGER trg_converted_source_read_only
            BEFORE UPDATE OR DELETE ON investments
            FOR EACH ROW EXECUTE FUNCTION conversion_source_read_only()
        """)
    elif dialect == "sqlite":
        for operation in ("UPDATE", "DELETE"):
            op.execute(f"""
                CREATE TRIGGER trg_converted_source_no_{operation.lower()}
                BEFORE {operation} ON investments
                WHEN EXISTS (
                    SELECT 1 FROM valuation_eligibility
                    WHERE owner_id = OLD.owner_id AND source_investment_id = OLD.id
                      AND representation = 'opening' AND status = 'active'
                )
                BEGIN SELECT RAISE(ABORT, 'converted original investment is read-only'); END
            """)
    else:
        raise RuntimeError("Conversion write guards require SQLite or PostgreSQL")

    def changed(fields):
        if dialect == "sqlite":
            return " OR ".join(f"NEW.{field} IS NOT OLD.{field}" for field in fields)
        return " OR ".join(f"NEW.{field} IS DISTINCT FROM OLD.{field}" for field in fields)

    conditions = {
        "reconciliation_approvals": (
            "(OLD.state = 'approved' AND NEW.state NOT IN ('approved', 'executed', 'expired')) OR "
            "(OLD.state = 'executed' AND NEW.state NOT IN ('executed', 'reversed')) OR "
            "(OLD.state IN ('reversed', 'expired') AND NEW.state != OLD.state) OR "
            "(OLD.executed_at IS NOT NULL AND (" + changed(["executed_at"]) + ")) OR "
            "(OLD.reversed_at IS NOT NULL AND (" + changed(["reversed_at"]) + ")) OR "
            "(NEW.state IN ('executed', 'reversed') AND "
            "(NEW.executed_at IS NULL OR NEW.execution_idempotency_key IS NULL OR "
            "NEW.execution_payload_sha256 IS NULL)) OR "
            "(NEW.state = 'reversed' AND NEW.reversed_at IS NULL)"
        ),
        "opening_positions": "(OLD.status = 'reversed' AND NEW.status != 'reversed')",
        "valuation_eligibility": (
            changed(["id", "owner_id", "source_investment_id", "opening_position_id",
                     "approval_id", "created_at"]) +
            " OR (OLD.status = 'reversed' AND "
            "(NEW.status != 'reversed' OR NEW.representation != 'legacy'))"
        ),
    }
    for table, condition in conditions.items():
        if dialect == "sqlite":
            op.execute(f"""
                CREATE TRIGGER trg_{table}_conversion_lifecycle
                BEFORE UPDATE ON {table} WHEN {condition}
                BEGIN SELECT RAISE(ABORT, 'conversion lifecycle is one-way'); END
            """)
        else:
            op.execute(f"""
                CREATE FUNCTION {table}_conversion_lifecycle() RETURNS trigger AS $$
                BEGIN
                    IF {condition} THEN
                        RAISE EXCEPTION 'conversion lifecycle is one-way';
                    END IF;
                    RETURN NEW;
                END;
                $$ LANGUAGE plpgsql
            """)
            op.execute(f"""
                CREATE TRIGGER trg_{table}_conversion_lifecycle
                BEFORE UPDATE ON {table}
                FOR EACH ROW EXECUTE FUNCTION {table}_conversion_lifecycle()
            """)


def downgrade_guards():
    dialect = op.get_bind().dialect.name
    for table in ("reconciliation_approvals", "opening_positions", "valuation_eligibility"):
        suffix = f" ON {table}" if dialect == "postgresql" else ""
        op.execute(f"DROP TRIGGER IF EXISTS trg_{table}_conversion_lifecycle{suffix}")
        if dialect == "postgresql":
            op.execute(f"DROP FUNCTION IF EXISTS {table}_conversion_lifecycle()")
    if dialect == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS trg_converted_source_read_only ON investments")
        op.execute("DROP FUNCTION IF EXISTS conversion_source_read_only()")
        for table in OWNER_TABLES:
            op.execute(f"DROP TRIGGER IF EXISTS trg_conversion_owner_write ON {table}")
        op.execute("DROP FUNCTION IF EXISTS conversion_owner_write_lock()")
    else:
        for operation in ("update", "delete"):
            op.execute(f"DROP TRIGGER IF EXISTS trg_converted_source_no_{operation}")