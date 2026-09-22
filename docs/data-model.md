# Serenity Data Model

This document is updated whenever a table changes.

## accounts

| Column | Type | Required | Notes |
|---|---|---|---|
| `id` | integer | auto | Primary key |
| `name` | text (≤100) | yes | e.g. "Everyday Checking" |
| `account_type` | text | yes | One of `ACCOUNT_TYPES` in `utils/choices.py` |
| `classification` | text | yes | Personal, Business, Investment, or Trading |
| `opening_balance_cents` | integer | yes (default 0) | Balance when tracking began, **in cents**. May be negative. |
| `institution` | text (≤100) | no | e.g. bank name |
| `notes` | text (≤1000) | no | |
| `created_at` | datetime (UTC) | auto | |
| `updated_at` | datetime (UTC) | auto | Updated on every change |

**Derived (not stored):**

- `current_balance` = `opening_balance` for now. Once transactions exist:
  `opening_balance + incoming transactions − outgoing transactions`.
  Calculated by `services/account_service.py → calculate_current_balance_cents()`.

**Temporary convention:** until Debt is modeled (Milestone 2), enter a credit
card's balance owed as a **negative** opening balance.

## Planned (next slice): transactions

```
Account 1 ──── * Transaction      (one account has many transactions)
```

`transactions.account_id` will reference `accounts.id`.
