"""
Dashboard service: combines the independent summaries into one view.

    api/dashboard.py -> services/dashboard_service.py
                          |-> account_service  (balances)
                          |-> finance_service  (bills, debts, investments)

This file only COMBINES numbers other services calculated. The one
formula it owns is net worth, and it works entirely in integer cents:
converting to dollars happens once, at the very end.
"""

from sqlalchemy.orm import Session

from schemas.dashboard import DashboardSummary
from services import account_service, finance_service
from utils.money import cents_to_dollars


def calculate_net_worth_cents(
    account_balance_cents: int,
    investment_value_cents: int,
    debt_balance_cents: int,
) -> int:
    """
    Net worth = what you have - what you owe:

        account balances + investment value - debt balances

    Notes on what is (and isn't) included, to avoid double counting:
    - Credit cards are Debts, never Accounts, so they're subtracted once.
    - Investments are the temporary starting-position records. Until the
      Portfolio milestone, a Brokerage/Retirement ACCOUNT balance should be
      its cash only, or the same money would count twice.
    - Prop-firm buying power must never be entered as an Account.
    """
    return account_balance_cents + investment_value_cents - debt_balance_cents


def get_dashboard_summary(db: Session) -> DashboardSummary:
    """Combine independent account and finance summaries for the dashboard."""
    accounts = account_service.list_accounts(db)
    account_totals = account_service.get_account_totals(db)
    debts = finance_service.list_debts(db)
    investments = finance_service.list_investments(db)
    finance = finance_service.get_finance_summary(db)
    return DashboardSummary(
        account_count=account_totals.account_count,
        total_balance=account_totals.total_balance,
        balance_by_classification=account_totals.balance_by_classification,
        bill_count=finance.bill_count,
        monthly_bill_total=finance.monthly_bill_total,
        debt_count=finance.debt_count,
        debt_balance=finance.debt_balance,
        investment_count=finance.investment_count,
        investment_value=finance.investment_value,
        net_worth=cents_to_dollars(
            calculate_net_worth_cents(
                account_service.total_balance_cents(accounts),
                finance_service.total_investment_value_cents(investments),
                finance_service.total_debt_balance_cents(debts),
            )
        ),
    )