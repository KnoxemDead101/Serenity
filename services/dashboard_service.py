from sqlalchemy.orm import Session

from schemas.dashboard import DashboardSummary
from services import account_service, finance_service
from utils.money import cents_to_dollars, dollars_to_cents


def get_dashboard_summary(db: Session) -> DashboardSummary:
    """Combine independent account and finance summaries for the dashboard."""
    accounts = account_service.get_account_totals(db)
    finance = finance_service.get_finance_summary(db)
    return DashboardSummary(
        account_count=accounts.account_count,
        total_balance=accounts.total_balance,
        balance_by_classification=accounts.balance_by_classification,
        bill_count=finance.bill_count,
        monthly_bill_total=finance.monthly_bill_total,
        debt_count=finance.debt_count,
        debt_balance=finance.debt_balance,
        investment_count=finance.investment_count,
        investment_value=finance.investment_value,
        net_worth=cents_to_dollars(
            dollars_to_cents(accounts.total_balance)
            + dollars_to_cents(finance.investment_value)
            - dollars_to_cents(finance.debt_balance)
        ),
    )