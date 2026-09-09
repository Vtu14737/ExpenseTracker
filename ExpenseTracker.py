import streamlit as st
import sqlite3
from datetime import date
from pathlib import Path
import pandas as pd

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide")

DB_PATH = Path(__file__).with_name("expenses.db")


def get_connection():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_date TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT DEFAULT '',
        amount REAL NOT NULL CHECK(amount >= 0)
    )""")
    conn.commit()
    return conn


conn = get_connection()


def load_expenses():
    return pd.read_sql_query(
        "SELECT id, expense_date, category, description, amount "
        "FROM expenses ORDER BY expense_date DESC, id DESC", conn
    )


st.title("💸 Expense Tracker")
st.caption("Record, analyze and manage your daily expenses.")
st.divider()

with st.sidebar:
    st.header("➕ Add Expense")
    with st.form("expense_form", clear_on_submit=True):
        expense_date = st.date_input("Date", value=date.today())
        category = st.selectbox(
            "Category",
            ["Food", "Travel", "Shopping", "Bills", "Health",
             "Entertainment", "Education", "Other"]
        )
        description = st.text_input("Description", placeholder="e.g. Lunch, bus ticket")
        amount = st.number_input("Amount (₹)", min_value=0.01, step=10.0, format="%.2f")
        submitted = st.form_submit_button("Add Expense", use_container_width=True, type="primary")
        if submitted:
            conn.execute(
                "INSERT INTO expenses (expense_date, category, description, amount) VALUES (?, ?, ?, ?)",
                (expense_date.isoformat(), category, description.strip(), amount),
            )
            conn.commit()
            st.success("Expense added!")
            st.rerun()
    st.divider()
    st.caption("Expenses are stored in SQLite.")

df = load_expenses()

total = float(df["amount"].sum()) if not df.empty else 0.0
count = len(df)
avg = float(df["amount"].mean()) if not df.empty else 0.0
this_month = 0.0
if not df.empty:
    this_month = float(df.loc[
        df["expense_date"].str.startswith(date.today().strftime("%Y-%m")), "amount"
    ].sum())

m1, m2, m3, m4 = st.columns(4)
m1.metric("Total Expenses", f"₹{total:,.2f}")
m2.metric("This Month", f"₹{this_month:,.2f}")
m3.metric("Transactions", f"{count:,}")
m4.metric("Average Expense", f"₹{avg:,.2f}")

if df.empty:
    st.info("No expenses recorded yet. Add your first expense from the sidebar.")
    st.stop()

st.subheader("🔎 Filter Expenses")
f1, f2, f3 = st.columns(3)
min_date = pd.to_datetime(df["expense_date"]).min().date()
max_date = pd.to_datetime(df["expense_date"]).max().date()

with f1:
    selected_dates = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
with f2:
    categories = sorted(df["category"].unique().tolist())
    selected_categories = st.multiselect("Category", categories, default=categories)
with f3:
    min_amount = st.number_input("Minimum amount (₹)", min_value=0.0, value=0.0, step=100.0)

filtered = df.copy()
if isinstance(selected_dates, tuple) and len(selected_dates) == 2:
    start_date, end_date = selected_dates
    filtered = filtered[
        (pd.to_datetime(filtered["expense_date"]).dt.date >= start_date)
        & (pd.to_datetime(filtered["expense_date"]).dt.date <= end_date)
    ]
filtered = filtered[filtered["category"].isin(selected_categories)]
filtered = filtered[filtered["amount"] >= min_amount]

st.subheader("📊 Spending Summary")
if filtered.empty:
    st.warning("No expenses match the selected filters.")
else:
    s1, s2 = st.columns([1, 2])
    with s1:
        st.metric("Filtered Total", f"₹{filtered['amount'].sum():,.2f}")
        st.metric("Filtered Transactions", f"{len(filtered):,}")
    with s2:
        category_totals = filtered.groupby("category")["amount"].sum().sort_values(ascending=False)
        st.bar_chart(category_totals, height=280)

st.subheader("📋 Expenses")
if not filtered.empty:
    display_df = filtered.copy()
    display_df["amount"] = display_df["amount"].map(lambda x: f"₹{x:,.2f}")
    display_df = display_df.rename(columns={
        "expense_date": "Date", "category": "Category",
        "description": "Description", "amount": "Amount"
    })
    st.dataframe(display_df[["Date", "Category", "Description", "Amount"]], use_container_width=True, hide_index=True)
    st.download_button(
        "⬇️ Download CSV",
        filtered.to_csv(index=False).encode("utf-8"),
        "expenses.csv",
        "text/csv",
    )

st.subheader("🗑️ Manage Expenses")
with st.expander("Delete an expense"):
    delete_options = {
        f"#{row.id} | {row.expense_date} | {row.category} | ₹{row.amount:,.2f}": int(row.id)
        for row in df.itertuples()
    }
    selected = st.selectbox("Select transaction", list(delete_options.keys()))
    if st.button("Delete selected expense"):
        conn.execute("DELETE FROM expenses WHERE id = ?", (delete_options[selected],))
        conn.commit()
        st.success("Expense deleted.")
        st.rerun()

st.caption("Expense Tracker • Data is stored locally in SQLite")
