"""Read-only counts and ownership check for an explicitly selected database."""

import os
import sys

from sqlalchemy import create_engine, inspect, text
from check_production_auth import check_auth

TABLES = (
    "accounts", "transactions", "transaction_corrections", "businesses",
    "dependents", "bills", "debts", "investments", "income_profiles",
)
IDENTITY_TABLES = ("users", "workspaces", "auth_identities")


def main() -> int:
    auth_result = check_auth()
    url = os.getenv("SERENITY_CHECK_DATABASE_URL", "").strip()
    if not url:
        print("Set SERENITY_CHECK_DATABASE_URL to the database to inspect.", file=sys.stderr)
        return 2
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url[len("postgresql://"):]
    engine = create_engine(url)
    rows_total = 0
    unowned_total = 0
    orphaned_total = 0
    try:
        with engine.connect() as connection:
            if connection.dialect.name == "postgresql":
                connection.execute(text("SET TRANSACTION READ ONLY"))
            inspector = inspect(connection)
            present = set(inspector.get_table_names())
            has_workspaces = "workspaces" in present
            version = None
            if "alembic_version" in present:
                version = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
            print(f"alembic_version: {version or '(none)'}")
            print(f"{'table':<28}{'rows':>8}  owner_id column  rows without owner"
                  + ("  rows not in a workspace" if has_workspaces else ""))
            for table in TABLES:
                if table not in present:
                    print(f"{table:<28}{'-':>8}  (table not present)")
                    continue
                count = connection.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar()
                columns = {item["name"] for item in inspector.get_columns(table)}
                if "owner_id" in columns:
                    unowned = connection.execute(text(
                        f"SELECT COUNT(*) FROM {table} "
                        "WHERE owner_id IS NULL OR trim(owner_id) = ''"
                    )).scalar()
                    owner_column = "yes"
                    if has_workspaces:
                        orphaned = connection.execute(text(
                            f"SELECT COUNT(*) FROM {table} WHERE owner_id IS NOT NULL "
                            "AND owner_id NOT IN (SELECT id FROM workspaces)"
                        )).scalar()
                    else:
                        orphaned = 0
                else:
                    unowned = count
                    owner_column = "NO"
                    orphaned = count if has_workspaces else 0
                rows_total += count
                unowned_total += unowned
                orphaned_total += orphaned
                print(f"{table:<28}{count:>8}  {owner_column:<15}  {unowned}"
                      + (f"  {orphaned}" if has_workspaces else ""))
            connection.rollback()
    finally:
        engine.dispose()
    if rows_total == 0:
        print("RESULT: no financial rows.")
    elif not unowned_total and not orphaned_total:
        print("RESULT: every row has a workspace owner."
              if has_workspaces else "RESULT: every row has an owner.")
    else:
        print(f"RESULT: {unowned_total} row(s) have no owner; {orphaned_total} "
              "row(s) are not linked to a workspace. Stop before publishing.")
    if version == "0011_identity_and_workspaces" and not set(IDENTITY_TABLES) <= present:
        print("RESULT: identity tables missing. Stop before publishing.")
        return 1
    return 0 if not unowned_total and not orphaned_total and not auth_result else 1


if __name__ == "__main__":
    sys.exit(main())