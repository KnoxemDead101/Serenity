#!/usr/bin/env bash
set -euo pipefail

if [[ "${SERENITY_DEVELOPMENT_DATABASE:-}" != "1" ]]; then
  echo "Refusing to run: set SERENITY_DEVELOPMENT_DATABASE=1 explicitly." >&2
  exit 1
fi
if [[ "${DATABASE_URL:-}" != postgresql://* && "${DATABASE_URL:-}" != postgres://* ]]; then
  echo "Refusing to run: DATABASE_URL must point to development PostgreSQL." >&2
  exit 1
fi

echo "Applying migrations to the explicitly selected development database..."
alembic upgrade head

read_revisions() {
  "$@" 2>/dev/null | grep -Eo 'Rev: [^ ]+' | cut -d' ' -f2 | sort -u
}
mapfile -t current < <(read_revisions alembic current --verbose)
mapfile -t heads < <(read_revisions alembic heads --verbose)
if ((${#current[@]} == 0 || ${#heads[@]} == 0)) ||
   ! diff -u <(printf '%s\n' "${current[@]}") <(printf '%s\n' "${heads[@]}") >/dev/null; then
  printf 'Migration mismatch. current: %s; heads: %s\n' \
    "${current[*]:-none}" "${heads[*]:-none}" >&2
  exit 1
fi

echo "Running tests..."
echo "Verifying browser tests are available..."
SERENITY_REQUIRE_BROWSER=1 pytest --collect-only -q \
  tests/test_responsive_browser.py tests/test_income_browser.py
SERENITY_REQUIRE_BROWSER=1 pytest -q
echo "Development checks passed. Publish still manages the production schema."