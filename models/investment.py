class Investment:
    def __init__(self, name, amount, interest_rate, maturity_date, date_invested=None):
        self.name = name
        self.amount = amount
        self.interest_rate = interest_rate
        self.maturity_date = maturity_date
        self.date_invested = date_invested

    def __str__(self):
        return f"Investment(name={self.name}, amount={self.amount}, interest_rate={self.interest_rate}, maturity_date={self.maturity_date}, date_invested={self.date_invested})"