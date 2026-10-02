#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

# Never migrate a caller-selected database. PostgreSQL tests create and destroy
# their own private cluster; all other database fixtures are isolated as well.
export DATABASE_URL=sqlite://
for variable in ${!PG@}; do unset "$variable"; done
export SERENITY_REQUIRE_POSTGRES=1
export SERENITY_REQUIRE_BROWSER=1

for tool in initdb postgres alembic python pytest; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "Required test tool missing: $tool. Restore the declared Replit dependencies before publishing." >&2
    exit 1
  fi
done
if ! command -v chromium >/dev/null 2>&1 &&
   ! command -v chromium-browser >/dev/null 2>&1 &&
   ! command -v google-chrome >/dev/null 2>&1; then
  echo "Required browser test tool missing: Chromium." >&2
  exit 1
fi
# Browser modules use importorskip, so check the import before collection.
python -c 'import psycopg; import playwright.sync_api' || {
  echo "Required test dependency missing: psycopg or Playwright." >&2
  exit 1
}

echo "Running required disposable PostgreSQL and browser checks..."
pytest -q
echo "Isolated prepublish checks passed. No existing database was migrated."
echo "Published Goals schema is NOT verified by this gate. After publishing, opt in to the separate read-only metadata check in docs/goals-production-review.md."