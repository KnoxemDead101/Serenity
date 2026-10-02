# Read-only reconciliation preview API

All routes described here require the current workspace session. These format 1
preview, verify and export operations do not persist approvals, execute, or
mutate finances. Cancel by discarding the response.

The separately authorized conversion implementation is documented in
[CONVERSION_IMPLEMENTATION.md](CONVERSION_IMPLEMENTATION.md). Its execution
preview and durable approvals do not reinterpret format 1 tokens or turn this
read-only API into execution authorization.

`POST /serenity-api/reconciliation/preview`

Request:
```json
{
  "mappings": [{
    "source_id": 1,
    "investment_account_id": 2,
    "instrument_id": 3,
    "specification_id": 4,
    "identity_confirmed": true,
    "beneficial_ownership": "personal",
    "basis_status": "unverified",
    "zero_basis_reviewed": false,
    "valuation_as_of": null,
    "valuation_evidence": null
  }],
  "accounts": [{
    "account_id": 5,
    "balance_meaning": "cash_only",
    "evidence": "Reviewed statement",
    "complete": true,
    "source_ids": [1],
    "cash_cents": 200000
  }]
}
```

Mappings may omit target IDs (unresolved); never match ticker automatically.
Ownership: `unknown|personal|simulation|prop|other`.
Basis: `unknown|unverified`; preserve original entered basis, do not claim verification.
Account meaning: `unknown|cash_only|combined`. Cash cents are strict integers.
For combined evidence, current ledger balance must equal cash cents plus original
values of ALL declared sources, every declared source must resolve to this account,
and every mapped source for this account must be declared. A complete declaration
is an explicit user attestation, not inferred from a partial batch.
Missing declarations or unresolved members block the entire account group.
Dates describe original entered values, not refreshed prices. Dated values require evidence.

Response: `{"report": {...}, "report_token": "signed immutable token"}`.
Report includes `format_version`, `captured_at`, `source_fingerprint`,
`sources` (all legacy sources, including unmapped/inactive, original `source`
snapshot, `mapping`, `outcome` = `eligible|unresolved|inactive`, `warnings`,
`current_value_cents`, `proposed_legacy_cents`, `proposed_holding_cents`,
`basis_cents`, `basis_status`, `valuation`),
`accounts` (all accounts with `current_balance_cents`, `proposed_balance_cents`,
`correction_cents`, `warnings`), `current`, `proposed`, `delta_cents`,
`explanations`, `warnings`, and `dependencies` (all owner financial/reference rows).
Totals have `account_balance_cents`, `legacy_investment_cents`,
`holding_value_cents`, `debt_balance_cents`, `net_worth_cents`.

`POST /serenity-api/reconciliation/verify` and
`POST /serenity-api/reconciliation/export` accept `{"report_token":"..."}`.
Verify returns `{"valid":true,"stale":false,"report":{...}}` when current,
or `{"valid":true,"stale":true,"report":{...}}` when dependencies changed.
Export returns the original signed envelope as a JSON attachment only if current;
stale exports return 409. Foreign IDs/reports or invalid signatures return 404.
Unknown/mismatched relationships return 404; duplicate declarations return 422.
Missing signing configuration returns 503. Tokens use SESSION_SECRET, domain-separated
from session signing; secret rotation invalidates old previews.