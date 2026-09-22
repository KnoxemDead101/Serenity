"""
Serenity command-line menu (the original prototype).

The web app (main.py) is now the main way to use Serenity. This menu is
kept for reference and learning. Run it with:  python cli.py
"""


def greeting():
    print("Hello! This is SerenityOS, your personal finance management system.")
    print("You can manage your bills, debts, and investments here.")
    print("Let's get started!")


def menu():
    while True:
        print("\nPlease choose an option:")
        print("1. Manage Bills")
        print("2. Manage Debts")
        print("3. Manage Investments")
        print("4. Exit")

        choice = input("Enter your choice (1-4): ")

        if choice == '1':

            while True:
                print("\nManage Bills:")
                print("1. Add a Bill")
                print("2. View Bills")
                print("3. Back to Main Menu")

                bill_choice = input("Enter your choice (1-3): ")

                if bill_choice == '1':
                    #add_bill()
                    pass
                elif bill_choice == '2':
                    #view_bills()
                    pass
                elif bill_choice == '3':
                    break
                else:
                    print("Invalid choice. Please try again.")

        elif choice == '2':
            #manage_debts()
            while True:
                print("\nManage Debts:")
                print("1. Add a Debt")
                print("2. View Debts")
                print("3. Back to Main Menu")

                debt_choice = input("Enter your choice (1-3): ")

                if debt_choice == '1':
                    #add_debt()
                    pass
                elif debt_choice == '2':
                    #view_debts()
                    pass
                elif debt_choice == '3':
                    break
                else:
                    print("Invalid choice. Please try again.")

        elif choice == '3':
            #manage_investments()
            while True:
                print("\nManage Investments:")
                print("1. Add an Investment")
                print("2. View Investments")
                print("3. Back to Main Menu")

                investment_choice = input("Enter your choice (1-3): ")

                if investment_choice == '1':
                    #add_investment()
                    pass
                elif investment_choice == '2':
                    #view_investments()
                    pass
                elif investment_choice == '3':
                    break
                else:
                    print("Invalid choice. Please try again.")
        elif choice == '4':
            print("Exiting SerenityOS. Goodbye!")
            break
        else:
            print("Invalid choice. Please try again.")




# This block only runs when you start this file directly:
#     python cli.py
# It does NOT run when another file imports cli.py.
if __name__ == "__main__":
    greeting()
    menu()
