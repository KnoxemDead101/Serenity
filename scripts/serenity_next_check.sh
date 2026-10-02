#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Wave 0 must prove disposable recovery, not silently skip the PostgreSQL
# round trip. The existing gate still owns database isolation and browser checks.
export SERENITY_REQUIRE_POSTGRES_RESTORE=1
unset TEST_POSTGRESQL_URL

echo "Running Serenity Next baseline: migrations, ownership, browsers, locking, and disposable recovery."
bash scripts/prepublish_check.sh
echo "Serenity Next engineering baseline passed."
echo "Production sign-in, live schema, off-host backups, key recovery, and broker execution are NOT certified by this gate."