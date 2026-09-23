"""
Fixed lists of allowed values ("choices").

Keeping these in one file means the backend validation, the API and
the frontend dropdowns all agree on the same options.

For v0.1 these are plain Python lists. Later they can become database
tables so the user can customize them (the handoff spec plans this for
transaction categories).
"""

ACCOUNT_TYPES = [
    "Checking",
    "Savings",
    "Cash",
    "Business Checking",
    "Brokerage",
    "Retirement",
    "Trading",
    "Other",
]

# Classification answers "what part of my financial life is this?"
ACCOUNT_CLASSIFICATIONS = [
    "Personal",
    "Business",
    "Investment",
    "Trading",
]

TRANSACTION_TYPES = ["Income", "Expense"]

TRANSACTION_CATEGORIES = [
    "Housing", "Insurance", "Education", "Subscriptions", "Utilities",
    "Transportation", "Car Maintenance", "Children", "Groceries", "Food",
    "Business Equipment", "Business Software", "Inventory", "Shipping",
    "Investment Contribution", "Dividend", "Trading Expense", "Other",
]

DEPENDENT_CATEGORIES = [
    "Food", "Clothing", "Medical", "Childcare",
    "Education", "Activities", "Supplies", "Other",
]

BILL_FREQUENCIES = [
    "Monthly",
    "Quarterly",
    "Annual",
    "One-time",
]

DEBT_TYPES = [
    "Credit Card",
    "Student Loan",
    "Personal Loan",
    "Mortgage",
    "Auto Loan",
    "Medical",
    "Other",
]

INCOME_TYPES = ["Hourly", "Salary", "Recurring", "Variable", "Other"]
PAY_PERIODS_PER_YEAR = {
    "Weekly": 52,
    "Biweekly": 26,
    "Semimonthly": 24,
    "Monthly": 12,
    "Annual": 1,
}
PAY_FREQUENCIES = list(PAY_PERIODS_PER_YEAR)
