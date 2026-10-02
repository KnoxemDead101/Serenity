# Owner-scoped Data Health

Data Health extends `/system` and `GET /serenity-api/system/health` with a
`data_health` object. Both retain verified session/workspace authorization and
`Cache-Control: no-store`. The API derives the owner only from verified
authorization, never a query parameter, request body or browser-selected ID.

This is evidence visibility, not a financial audit, score or operational-mode
controller. Runtime NORMAL/READ_ONLY/UNAVAILABLE remains the existing System
Health observation. Data Health does not change that state, authorize financial writes,
acquire financial write locks, modify records, migrate a database or repair
relationships. READ_ONLY can still have readable input evidence. If runtime
readability is unavailable, all data readings are unknown with null counts.

The separate explicit owner-check controls save verification evidence only.
Their owner-reviewed meaning, retention, snapshot binding and API are defined in
[MANUAL_VERIFICATION.md](MANUAL_VERIFICATION.md). They preserve financial
amounts, source edit timestamps and the existing write guard.

## Evidence contract

The response includes a UTC `checked_at`, a fixed boundary explanation and five
domain readings. Each contains a key, label, status, record count, basis,
allowlisted source-page link and findings (code, status, explanation).

| Status | Meaning |
| --- | --- |
| MISSING | The source was readable and has no stored records for this workspace. Count 0 describes stored records only; it does not confirm a real-world zero. |
| MANUAL | Stored inputs passed the checks listed below but remain manually entered, not verified external facts. |
| PARTIAL | Inputs are inactive-only, incomplete or excluded from a relevant projection/valuation; explanations state the gap. |
| STALE | A disclosed date-based review reminder, not an assertion that an amount is incorrect or that a payment was missed. |
| INCONSISTENT | Stored values or relationships failed the domain checks. Count is null; do not rely on the affected reading as a financial result. |
| UNAVAILABLE | Reliable reading failed. Count is null, never a fabricated zero or empty list. |

Findings may additionally be UNKNOWN for missing freshness evidence. Multiple
findings remain visible. The domain label prioritizes PARTIAL, then STALE, then
unknown coverage (PARTIAL), then MANUAL; it is not a severity score.
Unavailable/inconsistent readings replace that domain's evidence rather than
returning a partial count. Each domain uses a savepoint so a database SELECT
failure cannot poison later PostgreSQL readings. Messages never contain
exceptions, SQL, names, notes, IDs, balances, locations or valuation evidence.
Counts include inactive and draft source records, not only contributing assets.

## Checks and calculation boundaries

Input lists, read conversions, request validation, income projections and
investment selection reuse the canonical Python domain services and schemas.
No totals or monetary formulas are implemented in JavaScript. Existing
financial summaries and financial write semantics are unchanged.

| Source | Basis | Explanations |
| --- | --- | --- |
| Accounts (`/accounts`) | ACTUAL entered data | Opening balances without non-deleted actual transactions do not establish that no money moved. Non-deleted transactions must resolve to an account owned by this workspace and pass transaction validation. Current balance read conversion uses the existing cash correction and transaction formula. |
| Bills (`/finances`) | PLANNED | Recurring totals normalize schedules; they are not payment confirmations or actual expenses. One-time bills do not contribute to recurring totals. A past due date is a schedule-review reminder, not proof of non-payment. |
| Debts (`/finances`) | ACTUAL entered snapshots | Active entered balances are not lender-verified or payment-derived. Recorded zero is an input, not independent proof of no debt. |
| Investments (`/finances`) | MIXED candidates and entered holdings | Pending-review candidates are excluded from net worth. Canonical valuation selection uses eligible legacy values or selected openings, never both. Missing selected openings and missing owner-scoped portfolio/container links are inconsistent. Unknown/unverified opening cost basis does not establish realized profit. Reference calculations are not trades or live prices. |
| Income (`/income`) | PLANNED | Canonical projections do not post receipts. Variable income is not projected, not zero. Missing expected take-home produces unknown/partial net-income coverage, not a complete take-home total. Actual receipts remain account transactions. |

Common validation checks include canonical required fields, choices, money and
quantity bounds, income type-specific requirements and lifecycle validity.
Inactive inputs remain visible as evidence but do not become active financial
contributions. This is not an exhaustive integrity audit of every table,
historical event, correction, relationship, external statement or constraint.

## Date policy

The last-edit reminders below remain non-verification evidence. Explicit
matching owner checks now supersede the checked fact's edit-age or opening-age
reminder, with their own 30-UTC-calendar-day reminder. Missing checks remain
UNKNOWN even after edits; changed snapshots are not verified. Source and
conversion evidence validation still runs independently.

The initial fixed **30-day** interval is a disclosed manual review reminder,
not a market freshness SLA or a risk score. At exactly 30 days an active manual
account/debt/legacy valuation/income input becomes due for review. Last-edit
time can include note edits, so it cannot establish when a balance or price
was verified. Missing date evidence stays unknown and future timestamps are
inconsistent. SQLite persisted naive timestamps are interpreted as UTC.

Selected immutable openings use the **owner-evidenced valuation as-of date**,
not conversion capture time or a retained source's last edit. A missing
valuation date is UNKNOWN; a dated value without evidence or a future
valuation date is inconsistent. A valuation date 30 or more days old produces
a review reminder. Retained converted sources do not generate stale-value
reminders for the current selected representation.

An active bill date before today's UTC date produces a separate schedule
reminder; no payment status is inferred.

## Browser behavior and limits

The plain HTML page renders text, findings, basis, counts and allowlisted links.
Null counts explicitly say Unknown; zero counts explicitly say they are not
confirmed real-world zeros. Response validation rejects missing domains,
duplicates, invalid counts, contradictory status/findings, incorrect
basis/source associations and unsafe links. Loading and failed refresh clear
all previous evidence; session recovery removes the console. No returned text
is interpreted as HTML. Phone navigation and reduced motion remain supported.

Readings describe independently observed input evidence during a request, not
an immutable reconciliation report or a certificate against simultaneous
edits. No live-feed setup, published sign-in verification, automated/off-host
backup claim, production query, conversion execution/audit, Projects/Tasks
feature or publication is included.

## Verification

All fixtures are synthetic and disposable, including damaged SQLite schemas,
malformed financial rows and PostgreSQL SELECT-permission failures. Browser
tests exercise actual plain HTML, not a separate mock UI. Explicit owner-check
coverage is in `tests/test_verification*.py`.

```sh
SERENITY_REQUIRE_BROWSER=1 SERENITY_REQUIRE_POSTGRES=1 pytest -q \
  tests/test_data_health.py tests/test_data_health_browser.py \
  tests/test_system_health.py tests/test_system_browser.py \
  tests/test_system_health_postgres.py
bash scripts/prepublish_check.sh
```

The public running-app screenshot can only reach sign-in. Authenticated Data
Health rendering is covered with disposable authorized Chromium fixtures;
published signed-in UI remains a separate verification.

Baseline full-gate result before owner-check implementation on 2026-10-02:
**1,098 passed, 2 skipped**, exit status 0,
with two existing dependency deprecation warnings. Required Chromium and
disposable PostgreSQL checks ran. No existing database was migrated by the gate.