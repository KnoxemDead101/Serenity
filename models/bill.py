class Bill:
    def __init__(self, name, amount, due_date):
        self.name = name
        self.amount = amount
        self.due_date = due_date

    def __str__(self):
        return f"Bill(name={self.name}, amount={self.amount}, due_date={self.due_date})"

    def get_details(self):
        return {
            "name": self.name,
            "amount": self.amount,
            "due_date": self.due_date
        }
    #Getter functions for the properties of the Bill class
    def get_name(self):
        return self.name
    def get_amount(self):
        return self.amount
    def get_due_date(self):
        return self.due_date
    
    #Setter functions for the properties of the Bill class
    def set_name(self, name):
        self.name = name
    def set_amount(self, amount):
        self.amount = amount
    def set_due_date(self, due_date):
        self.due_date = due_date
    