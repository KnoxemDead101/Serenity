# Serenity

**Serenity** is a Python-based personal finance and investment intelligence application designed to provide a clear, organized view of a user's financial life.

Serenity goes beyond basic budgeting by bringing income, expenses, debt, bills, investments, receipts, and financial analysis into a single platform. The long-term goal is to transform financial data into useful insights, projections, and simulations that help users better understand their financial position and evaluate financial decisions.

## Purpose

Financial information is often spread across banking applications, brokerage accounts, bills, receipts, spreadsheets, and notes. Serenity is designed to organize that information into one structured system.

The application focuses on three principles:

* **Organization** — Keep important financial information structured and accessible.
* **Awareness** — Clearly show income, expenses, debt, investments, cash flow, and overall financial position.
* **Intelligence** — Analyze and simulate financial information to provide meaningful insights rather than simply storing numbers.

## Planned Features

### Income

* Hourly wage tracking
* Salary tracking
* Multiple income sources
* Weekly, monthly, and annual income calculations
* Projected income

### Budgeting

* Monthly budget creation
* Projected expenses
* Actual vs. projected spending
* Disposable income calculations
* Savings tracking

### Bills & Expenses

* Recurring bills
* Due dates
* Expense categories
* Fixed and variable expenses
* Monthly expense analysis

### Debt

* Current balances
* Interest rates
* Minimum payments
* Payment tracking
* Debt-to-income analysis
* Projected payoff calculations
* Future debt repayment simulations

### Investments

* Investment accounts
* Stocks and other equities
* Share quantities
* Average cost
* Manually updated market prices
* Cost basis
* Market value
* Unrealized gains and losses
* Portfolio allocation
* Overall portfolio analysis

Early versions of Serenity will support manually entered and simulated market prices. Live market-data integrations may be introduced in later versions.

### Receipt Tracking

Serenity will include a receipt-management system for connecting purchases with financial records.

Planned functionality includes:

* Merchant
* Purchase date
* Total
* Expense category
* Payment method
* Notes
* Receipt image/file storage

Future versions may introduce automated receipt processing and data extraction.

### Financial Analysis

Serenity will combine information from across the application to calculate metrics such as:

* Monthly cash flow
* Net worth
* Savings rate
* Debt-to-income ratio
* Investment allocation
* Portfolio performance
* Financial projections

## Technology

* **Python 3** with **FastAPI** (web/API layer)
* **SQLite** via **SQLAlchemy** (storage)
* **Pydantic** (input validation)
* Plain **HTML, CSS and JavaScript** (interface)
* **pytest** (automated testing)
* Git/GitHub (GitHub is the source of truth; Replit and Claude are development tools)

See [`docs/architecture.md`](docs/architecture.md) for how the pieces fit together
and [`docs/data-model.md`](docs/data-model.md) for the database tables.

## Running Serenity

Requires Python 3.10 or newer.

```bash
pip install -r requirements.txt
python main.py
```

Then open http://localhost:8000. Interactive API docs are at http://localhost:8000/docs.

**On Replit:** import this GitHub repository, set the Run command to `python main.py`,
install requirements if Replit doesn't do it automatically (`pip install -r requirements.txt`
in the Shell), and press Run.

Your data is saved to `serenity.db` in the project folder. That file is ignored by Git
so real financial data is never committed.

The original command-line menu is still available with `python cli.py`.

## Running the tests

```bash
pytest
```

Tests use a temporary in-memory database and never touch `serenity.db`.

## Development Philosophy

Serenity is being developed incrementally.

The initial goal is not to immediately create a large financial platform. Instead, each major system will be implemented and understood individually before additional complexity is introduced.

The initial development path is expected to include:

**Accounts + Transactions → Income, Bills, Debt, Budget → Portfolio → Trading Journal → Receipts → Scenarios/Projections**

Each milestone is built as a complete vertical slice (interface → API → validation → logic → database) before the next one begins.

This approach allows Serenity to remain usable throughout development while creating a foundation capable of supporting more advanced functionality later.

## Relationship to Brainiac

Serenity is also being developed as a financial intelligence component that may eventually integrate with **Brainiac**, a broader decision-intelligence engine.

Serenity's responsibility is to organize, calculate, track, and analyze financial information.

Brainiac's eventual responsibility is to reason across information from Serenity and other systems to support broader decision analysis and simulation.

In simple terms:

> **Serenity manages financial intelligence. Brainiac uses that intelligence to help evaluate decisions.**

## Project Status

**Status:** Early Development / Prototype

**Current milestone:** Milestone 1 (Accounts + Transactions).

- [x] Web app skeleton, SQLite storage, validation, tests
- [x] Accounts: create, list, dashboard totals
- [ ] Transactions: manual entry, classification, categories, history
- [ ] Dashboard: income vs. spending, recent transactions

## Vision

Serenity's long-term goal is to make complicated financial information easier to understand.

Instead of simply answering:

> "How much money do I have?"

Serenity should eventually help answer:

> "Where is my money going, how is my financial position changing, and what happens if I make this financial decision?"

That progression from **tracking → analysis → simulation → intelligence** defines the direction of Serenity.
