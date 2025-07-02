import datetime

expenses = []

def add_expense():
    category = input("Enter category (e.g., Food, Travel, Shopping): ")
    amount = float(input("Enter amount: ₹"))
    date = datetime.date.today()
    expenses.append({"category": category, "amount": amount, "date": date})
    print("✅ Expense added successfully!")

def view_expenses():
    if not expenses:
        print("No expenses recorded yet.")
        return
    print("\n--- All Expenses ---")
    for exp in expenses:
        print(f"{exp['date']} - {exp['category']}: ₹{exp['amount']}")

def total_by_category():
    if not expenses:
        print("No expenses to summarize.")
        return
    totals = {}
    for exp in expenses:
        cat = exp['category']
        totals[cat] = totals.get(cat, 0) + exp['amount']
    print("\n--- Total by Category ---")
    for cat, total in totals.items():
        print(f"{cat}: ₹{total}")

def filter_expenses():
    limit = float(input("Show expenses greater than ₹: "))
    filtered = [e for e in expenses if e["amount"] > limit]
    if not filtered:
        print(f"No expenses found over ₹{limit}.")
        return
    print(f"\n--- Expenses Over ₹{limit} ---")
    for e in filtered:
        print(f"{e['date']} - {e['category']}: ₹{e['amount']}")

# Main Program Loop
while True:
    print("\n📊 --- Expense Tracker ---")
    print("1. Add Expense")
    print("2. View All Expenses")
    print("3. View Total by Category")
    print("4. Filter Expenses")
    print("5. Exit")

    choice = input("Choose an option (1–5): ")

    if choice == '1':
        add_expense()
    elif choice == '2':
        view_expenses()
    elif choice == '3':
        total_by_category()
    elif choice == '4':
        filter_expenses()
    elif choice == '5':
        print("👋 Exiting Expense Tracker. Stay mindful with your money!")
        break
    else:
        print("❌ Invalid choice. Please try again.")
