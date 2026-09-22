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
    "Trading",
    "Credit Card",
    "Other",
]

# Classification answers "what part of my financial life is this?"
ACCOUNT_CLASSIFICATIONS = [
    "Personal",
    "Business",
    "Investment",
    "Trading",
]
