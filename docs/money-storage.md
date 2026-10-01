# Stored monetary limits

Every database field ending in `_cents` uses a signed 64-bit integer.
Migration `0013_money_bigint` widens all 11 such columns in PostgreSQL,
including nullable income profile amounts; SQLite integers already store
signed 64-bit values, so its tables are not rebuilt. The database change
does not change financial arithmetic, ownership, nullability, indexes, or
defaults. Explicitly run `alembic upgrade head` on the selected database
after backing it up, before running updated code. Replit publishing manages
the production schema separately; review proposed type changes before publishing.

`utils.validators.MAX_MONEY` is 1 trillion dollars per input, or
100 trillion cents. That fits a signed BIGINT (up to 9,223,372,036,854,775,807).
Income profile amounts are additionally capped at 20 million dollars per
input. Aggregated totals across unlimited records are calculated in Python;
the per-field limit does not cap aggregate totals.

Downgrading 0013 to 0012 checks **every** monetary column for values outside
the signed 32-bit range before changing any PostgreSQL column. If any value
would overflow, downgrade refuses to run. Back up first and never truncate
amounts to make a downgrade pass. SQLite's downgrade likewise checks values
but does not rebuild tables.