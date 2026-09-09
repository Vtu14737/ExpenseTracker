import streamlit as st
import sqlite3
from datetime import date
from pathlib import Path
import pandas as pd

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide", initial_sidebar_state="expanded")

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    .stApp { background: #f6f8fb; }
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1400px; }
    [data-testid="stSidebar"] { background: #111827; }
    [data-testid="stSidebar"] * { color: #f9fafb !important; }
    [data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-baseweb="select"] { background: #1f2937 !important; }
    .hero {
        background: linear-gradient(135deg, #111827 0%, #374151 100%);
        padding: 28px 32px; border-radius: 22px; margin-bottom: 24px;
        color: white; box-shadow: 0 12px 30px rgba(17,24,39,.14);
    }
    .hero h1 { margin: 0; font-size: 2.2rem; color: white; }
    .hero p { margin: 8px 0 0; color: #d1d5db; font-size: 1rem; }
    .metric-card {
        background: white; border: 1px solid #e5e7eb; border-radius: 18px;
        padding: 20px; min-height: 120px; box-shadow: 0 5px 18px rgba(15,23,42,.06);
    }
    .metric-label { color: #6b7280; font-size: .86rem; font-weight: 600; }
    .metric-value { color: #111827; font-size: 1.65rem; font-weight: 750; margin-top: 8px; }
    .section-title { color: #111827; font-size: 1.2rem; font-weight: 700; margin: 8px 0 14px; }
    .tip-card { background: white; border-radius: 16px; border: 1px solid #e5e7eb; padding: 16px 18px; }
    div[data-testid="stDataFrame"] { border-radius: 14px; overflow: hidden; }
    .stButton button, .stDownloadButton button { border-radius: 10px; font-weight: 600; }
    </style>
    """,
    unsafe_allow_html=True,
)

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


# -----------------------------
# Sidebar
# -----------------------------
with st.sidebar:
    st.markdown("# 💸 Expense Tracker")
    st.caption("Simple. Clean. In control.")
    st.divider()
    st.markdown("### ➕ Add New Expense")
    with st.form("expense_form", clear_on_submit=True):
        expense_date = st.date_input("Date", value=date.today())
        category = st.selectbox(
            "Category",
            ["Food", "Travel", "Shopping", "Bills", "Health", "Entertainment", "Education", "Other"],
        )
        description = st.text_input("Description", placeholder="Lunch, bus ticket, electricity...")
        amount = st.number_input("Amount (₹)", min_value=0.01, step=10.0, format="%.2f")
        submitted = st.form_submit_button("Add Expense  →", use_container_width=True, type="primary")
        if submitted:
            conn.execute(
                "INSERT INTO expenses (expense_date, category, description, amount) VALUES (?, ?, ?, ?)",
                (expense_date.isoformat(), category, description.strip(), amount),
            )
            conn.commit()
            st.success("Expense added successfully!")
            st.rerun()
    st.divider()
    st.caption("🔒 Your data is stored in the app's SQLite database.")

# -----------------------------
# Header
# -----------------------------
df = load_expenses()

total = float(df["amount"].sum()) if not df.empty else 0.0
count = len(df)
avg = float(df["amount"].mean()) if not df.empty else 0.0
this_month = 0.0
if not df.empty:
    this_month = float(df.loc[df["expense_date"].str.startswith(date.today().strftime("%Y-%m")), "amount"].sum())

st.markdown(
    '<div class="hero"><h1>Good money habits start here 👋</h1>'
    '<p>Track your spending, understand your habits, and stay on top of your budget.</p></div>',
    unsafe_allow_html=True,
)

# KPI cards
cols = st.columns(4)
metrics = [
    ("💰 Total Spent", f"₹{total:,.2f}"),
    ("📅 This Month", f"₹{this_month:,.2f}"),
    ("🧾 Transactions", f"{count:,}"),
    ("📈 Average Expense", f"₹{avg:,.2f}"),
]
for col, (label, value) in zip(cols, metrics):
    with col:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

st.write("")

if df.empty:
    st.markdown("### 🚀 Your dashboard is ready")
    st.info("No expenses recorded yet. Add your first expense using the form in the left sidebar.")
    st.stop()

# -----------------------------
# Filters
# -----------------------------
st.markdown('<div class="section-title">🔎 Filter & Explore</div>', unsafe_allow_html=True)
f1, f2, f3 = st.columns([1.2, 1, 1])
min_date = pd.to_datetime(df["expense_date"]).min().date()
max_date = pd.to_datetime(df["expense_date"]).max().date()

with f1:
    selected_dates = st.date_input("Date range", value=(min_date, max_date), min_value=min_date, max_value=max_date)
with f2:
    categories = sorted(df["category"].unique().tolist())
    selected_categories = st.multiselect("Categories", categories, default=categories)
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

# -----------------------------
# Analytics
# -----------------------------
st.markdown('<div class="section-title">📊 Spending Analytics</div>', unsafe_allow_html=True)
if filtered.empty:
    st.warning("No expenses match the selected filters.")
else:
    left, right = st.columns([1, 1.5])
    category_totals = filtered.groupby("category")["amount"].sum().sort_values(ascending=False)
    with left:
        st.markdown("**Top Spending Categories**")
        st.bar_chart(category_totals, height=300)
    with right:
        st.markdown("**Daily Spending Trend**")
        daily = filtered.assign(expense_date=pd.to_datetime(filtered["expense_date"])) \
            .groupby("expense_date")["amount"].sum().sort_index()
        st.line_chart(daily, height=300)

# -----------------------------
# Recent transactions
# -----------------------------
st.markdown('<div class="section-title">🧾 Recent Transactions</div>', unsafe_allow_html=True)
if not filtered.empty:
    display_df = filtered.head(15).copy()
    display_df["amount"] = display_df["amount"].map(lambda x: f"₹{x:,.2f}")
    display_df = display_df.rename(columns={
        "expense_date": "Date", "category": "Category", "description": "Description", "amount": "Amount"
    })
    st.dataframe(
        display_df[["Date", "Category", "Description", "Amount"]],
        use_container_width=True,
        hide_index=True,
        height=390,
    )
    b1, b2 = st.columns([1, 4])
    with b1:
        st.download_button(
            "⬇️ Export CSV",
            filtered.to_csv(index=False).encode("utf-8"),
            "expenses.csv",
            "text/csv",
            use_container_width=True,
        )
    with b2:
        st.caption(f"Showing {min(len(filtered), 15)} of {len(filtered)} matching transactions.")

# -----------------------------
# Manage data
# -----------------------------
with st.expander("⚙️ Manage Expenses"):
    delete_options = {
        f"#{row.id}  •  {row.expense_date}  •  {row.category}  •  ₹{row.amount:,.2f}": int(row.id)
        for row in df.itertuples()
    }
    selected = st.selectbox("Select a transaction to delete", list(delete_options.keys()))
    if st.button("Delete Selected Expense", type="secondary"):
        conn.execute("DELETE FROM expenses WHERE id = ?", (delete_options[selected],))
        conn.commit()
        st.success("Expense deleted.")
        st.rerun()

st.markdown("<br><center><small>Expense Tracker • Built with Streamlit • Keep tracking, keep improving 💸</small></center>", unsafe_allow_html=True)
