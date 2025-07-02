import streamlit as st
import datetime

# Initialize session state to store expenses
if 'expenses' not in st.session_state:
    st.session_state.expenses = []

st.set_page_config(page_title="💸 Expense Tracker", layout="centered")
st.title("💸 Expense Tracker")
st.write("Track your daily expenses with ease!")

# --- Add Expense ---
st.header("➕ Add Expense")
with st.form("expense_form"):
    category = st.text_input("Category (e.g., Food, Travel, Shopping)")
    amount = st.number_input("Amount (₹)", min_value=0.0, format="%.2f")
    submitted = st.form_submit_button("Add")
    if submitted and category:
        expense = {
            "category": category,
            "amount": amount,
            "date": datetime.date.today()
        }
        st.session_state.expenses.append(expense)
        st.success("✅ Expense added successfully!")

# --- View All Expenses ---
st.header("📋 All Expenses")
if st.session_state.expenses:
    for exp in st.session_state.expenses:
        st.write(f"• {exp['date']} - {exp['category']}: ₹{exp['amount']}")
else:
    st.info("No expenses recorded yet.")

# --- Total by Category ---
st.header("📊 Total by Category")
if st.session_state.expenses:
    totals = {}
    for exp in st.session_state.expenses:
        totals[exp['category']] = totals.get(exp['category'], 0) + exp['amount']
    for cat, total in totals.items():
        st.write(f"**{cat}**: ₹{total:.2f}")
else:
    st.info("No expenses to summarize.")

# --- Filter Expenses ---
st.header("🔎 Filter Expenses")
if st.session_state.expenses:
    limit = st.number_input("Show expenses greater than ₹", min_value=0.0, format="%.2f", key="filter_input")
    filtered = [e for e in st.session_state.expenses if e["amount"] > limit]
    if filtered:
        st.subheader(f"Expenses over ₹{limit}")
        for e in filtered:
            st.write(f"• {e['date']} - {e['category']}: ₹{e['amount']}")
    else:
        st.warning(f"No expenses found over ₹{limit}")
