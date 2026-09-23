from decimal import Decimal

from pydantic import BaseModel


class DashboardSummary(BaseModel):
    account_count: int
    total_balance: Decimal
    balance_by_classification: dict[str, Decimal]
    bill_count: int
    monthly_bill_total: Decimal
    debt_count: int
    debt_balance: Decimal
    investment_count: int
    investment_value: Decimal
    net_worth: Decimal