"""Publish-visible parent keys, verified only in a disposable PostgreSQL."""

from sqlalchemy import UniqueConstraint, text

from storage.database import Base
from test_money_postgres import _alembic, pg_engine, postgres_url  # noqa: F401

PARENT_KEYS = {
    "accounts": ("owner_id", "id"),
    "investments": ("owner_id", "id"),
    "investment_accounts": ("owner_id", "id"),
    "instruments": ("owner_id", "id"),
    "instrument_specifications": ("owner_id", "instrument_id", "id"),
}


def test_metadata_declares_publish_visible_owner_parent_constraints():
    for table, columns in PARENT_KEYS.items():
        assert any(
            isinstance(constraint, UniqueConstraint)
            and tuple(column.name for column in constraint.columns) == columns
            and constraint.name == f"uq_{table}_{'_'.join(columns)}"
            for constraint in Base.metadata.tables[table].constraints
        ), table


def test_postgres_parent_key_migration_preserves_rows_and_foreign_keys(
    postgres_url, pg_engine,
):
    _alembic(postgres_url, "upgrade", "0020_conversion_integration")
    with pg_engine.begin() as connection:
        connection.execute(text(
            "INSERT INTO accounts (owner_id, name, account_type, classification, "
            "opening_balance_cents, active, created_at, updated_at) VALUES "
            "('publish-key-test', 'Synthetic account', 'Checking', 'Personal', "
            "23456, true, now(), now())"
        ))

    def snapshots():
        with pg_engine.connect() as connection:
            rows = {
                table: connection.execute(text(
                    f"SELECT row_to_json(t)::text FROM {table} t ORDER BY id"
                )).scalars().all()
                for table in PARENT_KEYS
            }
            foreign_keys = connection.execute(text(
                "SELECT conname, conrelid, confrelid, conindid, "
                "pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE contype = 'f' ORDER BY conrelid, conname"
            )).all()
            indexes = connection.execute(text(
                "SELECT c.relname, i.indisunique, i.indisvalid, i.indisready "
                "FROM pg_index i JOIN pg_class c ON c.oid = i.indexrelid "
                "WHERE c.relname LIKE 'ux_%' ORDER BY c.relname"
            )).all()
        return rows, foreign_keys, indexes

    before = snapshots()
    _alembic(postgres_url, "upgrade", "0021_publish_parent_keys")
    assert snapshots() == before
    with pg_engine.connect() as connection:
        for table, columns in PARENT_KEYS.items():
            key = connection.execute(text(
                "SELECT c.contype, pg_get_constraintdef(c.oid), "
                "i.indisunique, i.indisvalid FROM pg_constraint c "
                "JOIN pg_index i ON i.indexrelid = c.conindid "
                "WHERE c.conrelid = to_regclass(:table) AND c.conname = :name"
            ), {
                "table": table, "name": f"uq_{table}_{'_'.join(columns)}",
            }).one()
            assert tuple(key) == (
                "u", f"UNIQUE ({', '.join(columns)})", True, True,
            )

    _alembic(postgres_url, "downgrade", "0020_conversion_integration")
    assert snapshots() == before
    _alembic(postgres_url, "upgrade", "head")