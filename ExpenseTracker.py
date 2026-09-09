import streamlit as st
import sqlite3
from datetime import date
from pathlib import Path
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide", initial_sidebar_state="expanded")

# -----------------------------
# Styling
# -----------------------------
st.markdown(
    """
    <style>
    .stApp { background: #f6f8fb; }
    .block-container { padding-top: 2rem; padding-bottom: 3rem; max-width: 1450px; }
    [data-testid="stSidebar"] { background: #111827; }
    [data-testid="stSidebar"] * { color: #f9fafb !important; }
    [data-testid="stSidebar"] input, [data-testid="stSidebar"] textarea,
    [data-testid="stSidebar"] [data-baseweb="select"] { background: #1f2937 !important; }
    .hero { background: linear-gradient(135deg, #111827 0%, #374151 100%); padding: 28px 32px; border-radius: 22px; margin-bottom: 24px; color: white; box-shadow: 0 12px 30px rgba(17,24,39,.14); }
    .hero h1 { margin: 0; font-size: 2.2rem; color: white; }
    .hero p { margin: 8px 0 0; color: #d1d5db; font-size: 1rem; }
    .metric-card { background: white; border: 1px solid #e5e7eb; border-radius: 18px; padding: 20px; min-height: 120px; box-shadow: 0 5px 18px rgba(15,23,42,.06); }
    .metric-label { color: #6b7280; font-size: .86rem; font-weight: 600; }
    .metric-value { color: #111827; font-size: 1.65rem; font-weight: 750; margin-top: 8px; }
    .section-title { color: #111827; font-size: 1.2rem; font-weight: 700; margin: 18px 0 14px; }
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
        "SELECT id, expense_date, category, description, amount FROM expenses ORDER BY expense_date DESC, id DESC", conn
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
        category = st.selectbox("Category", ["Food", "Travel", "Shopping", "Bills", "Health", "Entertainment", "Education", "Other"])
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
# Load data / header
# -----------------------------
df = load_expenses()

st.markdown(
    '<div class="hero"><h1>Good money habits start here 👋</h1><p>Track your spending and understand where your money goes.</p></div>',
    unsafe_allow_html=True,
)

total = float(df["amount"].sum()) if not df.empty else 0.0
count = len(df)
avg = float(df["amount"].mean()) if not df.empty else 0.0
this_month = float(df.loc[df["expense_date"].str.startswith(date.today().strftime("%Y-%m")), "amount"].sum()) if not df.empty else 0.0

cols = st.columns(4)
for col, (label, value) in zip(cols, [
    ("💰 Total Spent", f"₹{total:,.2f}"),
    ("📅 This Month", f"₹{this_month:,.2f}"),
    ("🧾 Transactions", f"{count:,}"),
    ("📈 Average Expense", f"₹{avg:,.2f}"),
]):
    with col:
        st.markdown(f'<div class="metric-card"><div class="metric-label">{label}</div><div class="metric-value">{value}</div></div>', unsafe_allow_html=True)

st.write("")

if df.empty:
    st.markdown("### 🚀 Your dashboard is ready")
    st.info("No expenses recorded yet. Add your first expense using the form in the left sidebar.")
    st.stop()

# Prepare date column once
df["expense_date"] = pd.to_datetime(df["expense_date"])

# -----------------------------
# Filters
# -----------------------------
st.markdown('<div class="section-title">🔎 Filter & Explore</div>', unsafe_allow_html=True)
f1, f2, f3 = st.columns([1.2, 1, 1])
min_date = df["expense_date"].min().date()
max_date = df["expense_date"].max().date()

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
    filtered = filtered[(filtered["expense_date"].dt.date >= start_date) & (filtered["expense_date"].dt.date <= end_date)]
filtered = filtered[filtered["category"].isin(selected_categories)]
filtered = filtered[filtered["amount"] >= min_amount]

if filtered.empty:
    st.warning("No expenses match the selected filters.")
    st.stop()

# -----------------------------
# Period selector + charts
# -----------------------------
st.markdown('<div class="section-title">📊 Expense Analytics</div>', unsafe_allow_html=True)
period = st.radio("View spending by", ["Daily", "Weekly", "Monthly", "Yearly"], horizontal=True)

chart_df = filtered.copy()

if period == "Daily":
    chart_df["period"] = chart_df["expense_date"].dt.strftime("%d %b %Y")
    chart_df["period_sort"] = chart_df["expense_date"].dt.normalize()
    period_label = "Daily Spending"
elif period == "Weekly":
    chart_df["period_sort"] = chart_df["expense_date"].dt.to_period("W").apply(lambda x: x.start_time)
    chart_df["period"] = chart_df["period_sort"].dt.strftime("%d %b") + " – " + chart_df["period_sort"].add(pd.Timedelta(days=6)).dt.strftime("%d %b")
    period_label = "Weekly Spending"
elif period == "Monthly":
    chart_df["period_sort"] = chart_df["expense_date"].dt.to_period("M").dt.to_timestamp()
    chart_df["period"] = chart_df["period_sort"].dt.strftime("%b %Y")
    period_label = "Monthly Spending"
else:
    chart_df["period_sort"] = chart_df["expense_date"].dt.to_period("Y").dt.to_timestamp()
    chart_df["period"] = chart_df["period_sort"].dt.strftime("%Y")
    period_label = "Yearly Spending"

trend = chart_df.groupby(["period_sort", "period"], as_index=False)["amount"].sum().sort_values("period_sort")

c1, c2 = st.columns([1.65, 1])
with c1:
    fig_bar = px.bar(trend, x="period", y="amount", title=f"{period_label} — Bar Graph", labels={"period": period, "amount": "Amount (₹)"}, text_auto=".2s")
    fig_bar.update_traces(hovertemplate="%{x}<br>₹%{y:,.2f}<extra></extra>")
    fig_bar.update_layout(height=390, margin=dict(l=20, r=20, t=60, b=20), plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig_bar, use_container_width=True)

with c2:
    category_totals = filtered.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
    fig_pie = px.pie(category_totals, names="category", values="amount", hole=0.48, title=f"Spending by Category — {period}")
    fig_pie.update_traces(textposition="inside", textinfo="percent+label", hovertemplate="%{label}<br>₹%{value:,.2f}<br>%{percent}<extra></extra>")
    fig_pie.update_layout(height=390, margin=dict(l=10, r=10, t=60, b=10), paper_bgcolor="white", legend_title_text="Category")
    st.plotly_chart(fig_pie, use_container_width=True)

# Trend line
st.markdown(f'<div class="section-title">📈 {period_label} Trend</div>', unsafe_allow_html=True)
fig_line = px.line(trend, x="period", y="amount", markers=True, labels={"period": period, "amount": "Amount (₹)"})
fig_line.update_traces(hovertemplate="%{x}<br>₹%{y:,.2f}<extra></extra>")
fig_line.update_layout(height=330, margin=dict(l=20, r=20, t=20, b=20), plot_bgcolor="white", paper_bgcolor="white")
st.plotly_chart(fig_line, use_container_width=True)

# Category ranking
st.markdown('<div class="section-title">🏆 Where Your Money Goes</div>', unsafe_allow_html=True)
rank_col1, rank_col2 = st.columns([1.5, 1])
with rank_col1:
    fig_rank = px.bar(category_totals.sort_values("amount"), x="amount", y="category", orientation="h", title="Category Ranking", labels={"amount": "Amount (₹)", "category": "Category"}, text_auto=".2s")
    fig_rank.update_layout(height=350, margin=dict(l=20, r=20, t=60, b=20), plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig_rank, use_container_width=True)
with rank_col2:
    period_total = float(trend["amount"].sum())
    highest_period = trend.loc[trend["amount"].idxmax()]
    st.markdown(f"**Selected period:** {period}")
    st.metric("Filtered Total", f"₹{period_total:,.2f}")
    st.metric("Highest Spending Period", str(highest_period["period"]), f"₹{highest_period['amount']:,.2f}")
    st.metric("Highest Category", str(category_totals.iloc[0]["category"]), f"₹{category_totals.iloc[0]['amount']:,.2f}")

# -----------------------------
# Transactions
# -----------------------------
st.markdown('<div class="section-title">🧾 Recent Transactions</div>', unsafe_allow_html=True)
display_df = filtered.sort_values(["expense_date", "id"], ascending=False).head(20).copy()
display_df["expense_date"] = display_df["expense_date"].dt.strftime("%d-%m-%Y")
display_df["amount"] = display_df["amount"].map(lambda x: f"₹{x:,.2f}")
display_df = display_df.rename(columns={"expense_date": "Date", "category": "Category", "description": "Description", "amount": "Amount"})
st.dataframe(display_df[["Date", "Category", "Description", "Amount"]], use_container_width=True, hide_index=True, height=390)

b1, b2 = st.columns([1, 4])
with b1:
    st.download_button("⬇️ Export CSV", filtered.to_csv(index=False).encode("utf-8"), "expenses.csv", "text/csv", use_container_width=True)
with b2:
    st.caption(f"Showing {min(len(filtered), 20)} of {len(filtered)} matching transactions.")

# -----------------------------
# Manage data
# -----------------------------
with st.expander("⚙️ Manage Expenses"):
    delete_options = {f"#{row.id}  •  {row.expense_date.strftime('%d-%m-%Y')}  •  {row.category}  •  ₹{row.amount:,.2f}": int(row.id) for row in df.itertuples()}
    selected = st.selectbox("Select a transaction to delete", list(delete_options.keys()))
    if st.button("Delete Selected Expense", type="secondary"):
        conn.execute("DELETE FROM expenses WHERE id = ?", (delete_options[selected],))
        conn.commit()
        st.success("Expense deleted.")
        st.rerun()

st.markdown("<br><center><small>Expense Tracker • Built with Streamlit • Keep tracking, keep improving 💸</small></center>", unsafe_allow_html=True)
