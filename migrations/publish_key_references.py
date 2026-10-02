"""Frozen ownership references used by the reviewed two-Publish repair."""

REFERENCES = (
    ("cash_reconciliation_entries", "fk_cash_reconciliation_entries_owner_account",
     ("owner_id", "account_id"), "accounts", ("owner_id", "id")),
    ("investment_accounts", "fk_investment_accounts_owner_account",
     ("owner_id", "account_id"), "accounts", ("owner_id", "id")),
    ("opening_positions", "fk_opening_positions_owner_account",
     ("owner_id", "cash_account_id"), "accounts", ("owner_id", "id")),
    ("opening_positions", "fk_opening_positions_owner_instrument",
     ("owner_id", "instrument_id"), "instruments", ("owner_id", "id")),
    ("opening_positions", "fk_opening_positions_owner_source",
     ("owner_id", "source_investment_id"), "investments", ("owner_id", "id")),
    ("opening_positions", "fk_opening_positions_owner_specification",
     ("owner_id", "instrument_id", "specification_id"),
     "instrument_specifications", ("owner_id", "instrument_id", "id")),
    ("valuation_eligibility", "fk_valuation_eligibility_owner_source",
     ("owner_id", "source_investment_id"), "investments", ("owner_id", "id")),
)


def restore_references(operations):
    from sqlalchemy import inspect

    connection = operations.get_bind()
    for table, name, columns, parent, parent_columns in REFERENCES:
        existing = {
            fk["name"]: fk for fk in inspect(connection).get_foreign_keys(table)
        }
        if name in existing:
            fk = existing[name]
            if (
                tuple(fk["constrained_columns"]) != columns
                or fk["referred_table"] != parent
                or tuple(fk["referred_columns"]) != parent_columns
                or fk["options"].get("ondelete") != "RESTRICT"
            ):
                raise RuntimeError(f"Unexpected definition for ownership key {name}")
        if name not in existing:
            operations.create_foreign_key(
                name, table, parent, list(columns), list(parent_columns),
                ondelete="RESTRICT",
            )