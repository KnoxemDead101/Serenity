class Income:
    def __init__(self, source, amount, date_received, hourly_rate=None, hours_worked=None, salary=None):
        self.source = source
        self.amount = amount
        self.date_received = date_received
        self.hourly_rate = hourly_rate
        self.hours_worked = hours_worked
        self.salary = salary

    def __str__(self):
        return f"Income(source={self.source}, amount={self.amount}, date_received={self.date_received}, hourly_rate={self.hourly_rate}, hours_worked={self.hours_worked}, salary={self.salary})"
