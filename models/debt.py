class Debt:
    def __init__(self, name, amount, description, interest_rate, due_date):
        self.name = name
        self.amount = amount
        self.description = description
        self.interest_rate = interest_rate
        self.due_date = due_date

    def __str__(self):
        return f"Debt(name={self.name}, amount={self.amount}, description={self.description}, interest_rate={self.interest_rate}, due_date={self.due_date})"