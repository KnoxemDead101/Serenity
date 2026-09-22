# Serenity Architecture (v0.1)

## The layers

Every feature follows the same path. Each folder has one job.

```
frontend/  (HTML, CSS, JS)        what the user sees; fetches and displays only
     |  HTTP + JSON
     v
api/        (FastAPI routes)       receives requests, returns responses
     |
     v
schemas/    (Pydantic)             validates input, defines output shape
     |
     v
services/   (plain Python)         business rules and financial calculations
     |
     v
models/     (SQLAlchemy)           database table definitions
     |
     v
storage/    (database.py)          connection to SQLite (serenity.db)

utils/      shared helpers used by several layers: money, validators, choices
tests/      automated checks for all of the above
```

**Rule of thumb:** if code calculates a financial number, it belongs in
`services/` (or `utils/money.py`), never in `frontend/` or `api/`.

## Walkthrough: creating an account

1. **`frontend/accounts.html`**: the user fills in the form and clicks *Add account*.
2. **`frontend/static/js/accounts.js`**: reads the form and calls
   `apiPost("/api/accounts", {...})`. The balance is sent as a string, like `"1500.00"`.
3. **`main.py`**: FastAPI matches the URL to the router from `api/accounts.py`.
4. **`schemas/account.py` → `AccountCreate`**: Pydantic checks every field using
   the functions in `utils/validators.py`. If anything is wrong, FastAPI returns
   **HTTP 422** with the reason, and steps 5–7 never happen.
5. **`api/accounts.py` → `create_account()`**: calls the service.
6. **`services/account_service.py` → `create_account()`**: converts dollars to
   cents (`utils/money.py`), builds an `Account` object, and commits it.
7. **`models/account.py` + `storage/database.py`**: SQLAlchemy writes a row
   to the `accounts` table in `serenity.db`.
8. The service converts the saved row into an `AccountRead` (cents → dollars,
   plus the calculated `current_balance`). FastAPI returns it as JSON with
   **HTTP 201 Created**.
9. **`accounts.js`** shows a success message and reloads the table using
   `GET /api/accounts`.

## Walkthrough: dashboard totals

`frontend/index.html` → `dashboard.js` → `GET /api/dashboard/summary` →
`account_service.get_account_totals()`, which loops over all accounts and
adds up `calculate_current_balance_cents()` per classification → JSON → cards.

Nothing on the dashboard is stored. It is recalculated on every page load.

## Key decisions

| Decision | Why |
|---|---|
| Money stored as integer **cents** | Floats can't represent many decimal values exactly (0.1 + 0.2 ≠ 0.3). |
| Money sent over the API as **strings** (`"12.34"`) | Keeps exact precision between Python's `Decimal` and the browser. |
| **Current balance is calculated**, not stored | One source of truth: opening balance + transactions. |
| Amounts with more than 2 decimals are **rejected**, not rounded | Silently changing financial numbers is worse than asking. |
| `models/` and `schemas/` are separate | The database shape and the API shape can change independently. |
| Allowed values live in `utils/choices.py` | Backend validation and frontend dropdowns share one list. |
| No framework on the frontend | Plain JS is enough for v0.1 and keeps the data flow visible. |

## Other files

- `cli.py`: the original command-line menu, kept for reference.
- `models/bill.py`, `debt.py`, `income.py`, `investment.py`: early plain
  classes. They will become database models in Milestone 2.
