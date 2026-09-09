import streamlit as st
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px
from sqlalchemy import text

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide", initial_sidebar_state="expanded")

DB_PATH = Path(__file__).with_name("expenses.db")
DEFAULT_CATEGORIES = ["Food", "Travel", "Shopping", "Bills", "Health", "Entertainment", "Education", "Rent", "Groceries", "Fuel", "Subscriptions", "Other"]


def get_cloud_connection():
    """Use PostgreSQL when a Streamlit SQL connection secret is configured."""
    try:
        if "connections" in st.secrets and "neon" in st.secrets["connections"]:
            return st.connection("neon", type="sql")
    except Exception:
        pass
    return None


cloud_conn = get_cloud_connection()
using_cloud_db = cloud_conn is not None


def sqlite_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_cloud_db():
    statements = [
        """CREATE TABLE IF NOT EXISTS expenses(
            id SERIAL PRIMARY KEY,
            expense_date DATE NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0))""",
        """CREATE TABLE IF NOT EXISTS categories(
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS income(
            id SERIAL PRIMARY KEY,
            income_date DATE NOT NULL,
            source TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0))""",
        """CREATE TABLE IF NOT EXISTS category_budgets(
            category TEXT PRIMARY KEY,
            amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0))""",
        """CREATE TABLE IF NOT EXISTS app_settings(
            setting_key TEXT PRIMARY KEY,
            setting_value TEXT NOT NULL)""",
    ]
    with cloud_conn.session as session:
        for sql in statements:
            session.execute(text(sql))
        for item in DEFAULT_CATEGORIES:
            session.execute(text("INSERT INTO categories(name) VALUES(:name) ON CONFLICT(name) DO NOTHING"), {"name": item})
        session.commit()


def init_sqlite_db():
    conn = sqlite_connection()
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        expense_date TEXT NOT NULL,
        category TEXT NOT NULL,
        description TEXT DEFAULT '',
        amount REAL NOT NULL CHECK(amount >= 0))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS categories(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS income(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        income_date TEXT NOT NULL,
        source TEXT NOT NULL,
        description TEXT DEFAULT '',
        amount REAL NOT NULL CHECK(amount >= 0))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS category_budgets(
        category TEXT PRIMARY KEY,
        amount REAL NOT NULL CHECK(amount >= 0))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS app_settings(
        setting_key TEXT PRIMARY KEY,
        setting_value TEXT NOT NULL)""")
    for item in DEFAULT_CATEGORIES:
        conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (item,))
    conn.commit()
    return conn


if using_cloud_db:
    init_cloud_db()
else:
    local_conn = init_sqlite_db()


def migrate_sqlite_to_cloud():
    """One-time migration of an existing local SQLite DB into PostgreSQL."""
    if not using_cloud_db or not DB_PATH.exists():
        return 0

    try:
        source = sqlite3.connect(DB_PATH)
        source.row_factory = sqlite3.Row
        migrated = 0
        with cloud_conn.session as session:
            existing = session.execute(text("SELECT COUNT(*) FROM expenses")).scalar() or 0
            if existing == 0:
                for row in source.execute("SELECT expense_date, category, description, amount FROM expenses ORDER BY id"):
                    session.execute(text("INSERT INTO expenses(expense_date,category,description,amount) VALUES(:d,:c,:x,:a)"), dict(d=row[0], c=row[1], x=row[2] or "", a=row[3]))
                    migrated += 1

            existing_income = session.execute(text("SELECT COUNT(*) FROM income")).scalar() or 0
            if existing_income == 0:
                for row in source.execute("SELECT income_date, source, description, amount FROM income ORDER BY id"):
                    session.execute(text("INSERT INTO income(income_date,source,description,amount) VALUES(:d,:s,:x,:a)"), dict(d=row[0], s=row[1], x=row[2] or "", a=row[3]))

            existing_categories = session.execute(text("SELECT COUNT(*) FROM categories")).scalar() or 0
            if existing_categories <= len(DEFAULT_CATEGORIES):
                for row in source.execute("SELECT name FROM categories"):
                    session.execute(text("INSERT INTO categories(name) VALUES(:name) ON CONFLICT(name) DO NOTHING"), {"name": row[0]})

            for row in source.execute("SELECT category, amount FROM category_budgets"):
                session.execute(text("INSERT INTO category_budgets(category,amount) VALUES(:c,:a) ON CONFLICT(category) DO UPDATE SET amount=EXCLUDED.amount"), dict(c=row[0], a=row[1]))

            try:
                row = source.execute("SELECT setting_value FROM app_settings WHERE setting_key='monthly_budget'").fetchone()
                if row:
                    session.execute(text("INSERT INTO app_settings(setting_key,setting_value) VALUES('monthly_budget',:v) ON CONFLICT(setting_key) DO NOTHING"), {"v": row[0]})
            except Exception:
                pass
            session.commit()
        source.close()
        return migrated
    except Exception:
        return 0


if using_cloud_db:
    migrated_count = migrate_sqlite_to_cloud()
    if migrated_count:
        st.toast(f"Migrated {migrated_count} existing expenses to cloud storage.", icon="☁️")


def query_df(sql, params=None):
    if using_cloud_db:
        return cloud_conn.query(sql, params=params or {}, ttl=0)
    return pd.read_sql_query(sql, local_conn, params=params or {})


def execute(sql, params=None):
    if using_cloud_db:
        with cloud_conn.session as session:
            session.execute(text(sql), params or {})
            session.commit()
    else:
        local_conn.execute(sql, tuple((params or {}).values()) if params else ())
        local_conn.commit()


def load_expenses():
    return query_df("SELECT id, expense_date, category, description, amount FROM expenses ORDER BY expense_date DESC, id DESC")


def load_income():
    return query_df("SELECT id, income_date, source, description, amount FROM income ORDER BY income_date DESC, id DESC")


def load_categories():
    df = query_df("SELECT name FROM categories ORDER BY id")
    return df["name"].tolist() if not df.empty else DEFAULT_CATEGORIES


def load_category_budgets():
    df = query_df("SELECT category, amount FROM category_budgets ORDER BY category")
    return {r.category: float(r.amount) for r in df.itertuples()} if not df.empty else {}


def get_monthly_budget():
    df = query_df("SELECT setting_value FROM app_settings WHERE setting_key='monthly_budget'")
    return float(df.iloc[0, 0]) if not df.empty else 20000.0


def save_monthly_budget(amount):
    if using_cloud_db:
        execute("INSERT INTO app_settings(setting_key,setting_value) VALUES('monthly_budget',:v) ON CONFLICT(setting_key) DO UPDATE SET setting_value=EXCLUDED.setting_value", {"v": str(amount)})
    else:
        execute("INSERT OR REPLACE INTO app_settings(setting_key,setting_value) VALUES(?,?)", {"a": "monthly_budget", "b": str(amount)})


def add_expense(expense_date, category, description, amount):
    if using_cloud_db:
        execute("INSERT INTO categories(name) VALUES(:c) ON CONFLICT(name) DO NOTHING", {"c": category})
        execute("INSERT INTO expenses(expense_date,category,description,amount) VALUES(:d,:c,:x,:a)", {"d": expense_date.isoformat(), "c": category, "x": description.strip(), "a": amount})
    else:
        local_conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (category,))
        local_conn.execute("INSERT INTO expenses(expense_date,category,description,amount) VALUES(?,?,?,?)", (expense_date.isoformat(), category, description.strip(), amount))
        local_conn.commit()


def add_income(income_date, source, description, amount):
    execute("INSERT INTO income(income_date,source,description,amount) VALUES(:d,:s,:x,:a)" if using_cloud_db else "INSERT INTO income(income_date,source,description,amount) VALUES(?,?,?,?)", {"d": income_date.isoformat(), "s": source, "x": description.strip(), "a": amount})


def delete_expense(expense_id):
    if using_cloud_db:
        execute("DELETE FROM expenses WHERE id=:id", {"id": expense_id})
    else:
        local_conn.execute("DELETE FROM expenses WHERE id=?", (expense_id,)); local_conn.commit()


def delete_income(income_id):
    if using_cloud_db:
        execute("DELETE FROM income WHERE id=:id", {"id": income_id})
    else:
        local_conn.execute("DELETE FROM income WHERE id=?", (income_id,)); local_conn.commit()


def update_expense(expense_id, expense_date, category, description, amount):
    if using_cloud_db:
        execute("INSERT INTO categories(name) VALUES(:c) ON CONFLICT(name) DO NOTHING", {"c": category})
        execute("UPDATE expenses SET expense_date=:d,category=:c,description=:x,amount=:a WHERE id=:id", {"d": expense_date.isoformat(), "c": category, "x": description.strip(), "a": amount, "id": expense_id})
    else:
        local_conn.execute("UPDATE expenses SET expense_date=?,category=?,description=?,amount=? WHERE id=?", (expense_date.isoformat(), category, description.strip(), amount, expense_id))
        local_conn.execute("INSERT OR IGNORE INTO categories(name) VALUES(?)", (category,)); local_conn.commit()


def save_category_budget(category, amount):
    if using_cloud_db:
        if amount > 0:
            execute("INSERT INTO category_budgets(category,amount) VALUES(:c,:a) ON CONFLICT(category) DO UPDATE SET amount=EXCLUDED.amount", {"c": category, "a": amount})
        else:
            execute("DELETE FROM category_budgets WHERE category=:c", {"c": category})
    else:
        if amount > 0:
            local_conn.execute("INSERT OR REPLACE INTO category_budgets(category,amount) VALUES(?,?)", (category, amount))
        else:
            local_conn.execute("DELETE FROM category_budgets WHERE category=?", (category,))
        local_conn.commit()


if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None


dark = st.session_state.dark_mode
if dark:
    app_bg, card_bg, text, muted, border, plot_bg, input_bg = "#0b1120", "#111827", "#f9fafb", "#cbd5e1", "#374151", "#111827", "#1f2937"
else:
    app_bg, card_bg, text, muted, border, plot_bg, input_bg = "#f5f7fb", "#ffffff", "#111827", "#4b5563", "#e5e7eb", "#ffffff", "#ffffff"

st.markdown(f"""
<style>
.stApp,[data-testid="stAppViewContainer"]{{background:{app_bg}!important;color:{text}!important}}
.block-container{{max-width:1450px;padding-top:1.6rem}}
.main *,section.main,section.main p,section.main span,section.main label,section.main h1,section.main h2,section.main h3,section.main h4,section.main h5,section.main h6,section.main [data-testid="stMarkdownContainer"]{{color:{text}}}
.main .stCaption,section.main [data-testid="stCaptionContainer"]{{color:{muted}!important}}
[data-testid="stSidebar"]{{background:#111827!important}} [data-testid="stSidebar"] *,[data-testid="stSidebar"] label,[data-testid="stSidebar"] p,[data-testid="stSidebar"] span{{color:#f9fafb!important}}
section.main input,section.main textarea{{background:{input_bg}!important;color:{text}!important;caret-color:{text}!important}}
section.main input::placeholder,section.main textarea::placeholder{{color:{muted}!important;opacity:1!important}}
section.main [data-baseweb="select"]>div,section.main [data-baseweb="input"]>div,section.main [data-baseweb="textarea"]>div{{background:{input_bg}!important;color:{text}!important;border-color:{border}!important}}
section.main [data-baseweb="select"] *,section.main [data-baseweb="input"] *,section.main [data-baseweb="textarea"] *{{color:{text}!important}}
.hero{{background:linear-gradient(135deg,#111827,#4f46e5);padding:30px 34px;border-radius:24px;color:white;margin-bottom:22px;box-shadow:0 12px 30px #00000018}} .hero h1,.hero p{{color:white!important}} .hero h1{{margin:0;font-size:2rem}} .hero p{{margin:7px 0 0;color:#e5e7eb!important}}
.card{{background:{card_bg};border:1px solid {border};border-radius:18px;padding:19px;box-shadow:0 5px 18px #0f172a18;min-height:115px}} .label{{font-size:.82rem;color:{muted}!important;font-weight:650}} .value{{font-size:1.55rem;color:{text}!important;font-weight:750;margin-top:7px}} .section{{font-size:1.18rem;font-weight:750;color:{text}!important;margin:22px 0 12px}} .insight{{background:{card_bg};border:1px solid {border};border-radius:16px;padding:15px 17px;height:100%;color:{text}!important}} .insight *{{color:{text}!important}} .insight small{{color:{muted}!important}}
section.main [data-testid="stDataFrame"]{{border:1px solid {border}!important}} section.main [data-testid="stDataFrame"] *{{color:{text}!important}}
.stButton button,.stDownloadButton button,[data-testid="stFormSubmitButton"] button{{border-radius:12px!important;font-weight:700!important;min-height:42px!important;transition:all .18s ease!important;box-shadow:0 4px 12px rgba(15,23,42,.10)!important;border:1px solid rgba(148,163,184,.35)!important;cursor:pointer!important}} .stButton button:hover,.stDownloadButton button:hover,[data-testid="stFormSubmitButton"] button:hover{{transform:translateY(-2px)!important;box-shadow:0 8px 20px rgba(15,23,42,.18)!important;border-color:#6366f1!important}}
[data-testid="stFormSubmitButton"] button[kind="primary"]{{background:linear-gradient(135deg,#6366f1,#8b5cf6)!important;color:white!important;border:none!important}} .delete-btn button{{background:#fff1f2!important;color:#dc2626!important;border-color:#fecdd3!important}} .edit-btn button{{background:#eef2ff!important;color:#4338ca!important;border-color:#c7d2fe!important}}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("# 💸 Expense Tracker")
    st.caption("Personal finance dashboard")
    if using_cloud_db:
        st.success("☁️ Cloud database connected", icon="☁️")
    else:
        st.warning("💾 Local database mode", icon="⚠️")
    st.divider()
    st.toggle("🌙 Dark mode", key="dark_mode")

    st.markdown("### ➕ Add Expense")
    categories = load_categories()
    with st.form("expense_form", clear_on_submit=True):
        expense_date = st.date_input("Date", value=date.today(), key="new_expense_date")
        category = st.selectbox("Category", categories, accept_new_options=True, help="Choose an example category or type your own category and press Enter.")
        description = st.text_input("Description", placeholder="Lunch, fuel, electricity...")
        amount = st.number_input("Amount (₹)", min_value=0.01, step=10.0, format="%.2f")
        if st.form_submit_button("Add Expense  →", use_container_width=True, type="primary"):
            category = str(category).strip()
            if category:
                add_expense(expense_date, category, description, amount)
                st.success("Expense added!")
                st.rerun()
            else:
                st.error("Please enter a category.")
    st.caption("💡 Examples are provided. You can also type and add your own category.")

    st.divider()
    st.markdown("### 💵 Add Income")
    with st.form("income_form", clear_on_submit=True):
        income_date = st.date_input("Date", value=date.today(), key="new_income_date")
        source = st.selectbox("Source", ["Salary", "Freelance", "Business", "Interest", "Gift", "Refund", "Other"], key="income_source")
        income_description = st.text_input("Description", placeholder="September salary, freelance work...")
        income_amount = st.number_input("Amount (₹)", min_value=0.01, step=100.0, format="%.2f", key="income_amount")
        if st.form_submit_button("Add Income  →", use_container_width=True):
            add_income(income_date, source, income_description, income_amount)
            st.success("Income added!")
            st.rerun()

    st.divider()
    st.markdown("### 🎯 Monthly Budget")
    budget = st.number_input("Overall Budget (₹)", min_value=0.0, value=get_monthly_budget(), step=1000.0)
    if budget != get_monthly_budget():
        save_monthly_budget(budget)
        st.rerun()

    st.markdown("### 🎯 Category Budgets")
    existing_budgets = load_category_budgets()
    selected_budget_category = st.selectbox("Category", load_categories(), key="budget_category")
    category_budget_value = st.number_input("Monthly limit (₹)", min_value=0.0, value=float(existing_budgets.get(selected_budget_category, 0.0)), step=500.0, key="category_budget_value")
    if st.button("Save Category Budget", use_container_width=True):
        save_category_budget(selected_budget_category, category_budget_value)
        st.success("Category budget saved!")
        st.rerun()
    st.caption("Set ₹0 to remove a category budget.")


df = load_expenses()
income_df = load_income()
today = date.today()
if not df.empty:
    df["expense_date"] = pd.to_datetime(df["expense_date"])
    df["amount"] = pd.to_numeric(df["amount"])
if not income_df.empty:
    income_df["income_date"] = pd.to_datetime(income_df["income_date"])
    income_df["amount"] = pd.to_numeric(income_df["amount"])

st.markdown('<div class="section">🔎 Search & Filters</div>', unsafe_allow_html=True)
f1, f2, f3, f4 = st.columns([2.1, 1.5, 1.5, 1.2])
with f1:
    search_text = st.text_input("Search", placeholder="Search description or category...", label_visibility="collapsed")
with f2:
    filter_categories = st.multiselect("Category", load_categories(), placeholder="All categories", label_visibility="collapsed")
with f3:
    filter_period = st.selectbox("Period", ["All time", "This month", "Last 30 days", "This year"], label_visibility="collapsed")
with f4:
    sort_order = st.selectbox("Sort", ["Newest", "Highest amount", "Lowest amount"], label_visibility="collapsed")

filtered_df = df.copy()
if not filtered_df.empty:
    if search_text:
        term = search_text.lower()
        filtered_df = filtered_df[filtered_df["category"].str.lower().str.contains(term, na=False) | filtered_df["description"].fillna("").str.lower().str.contains(term, na=False)]
    if filter_categories:
        filtered_df = filtered_df[filtered_df["category"].isin(filter_categories)]
    if filter_period == "This month":
        filtered_df = filtered_df[filtered_df["expense_date"].dt.to_period("M") == pd.Period(today, freq="M")]
    elif filter_period == "Last 30 days":
        filtered_df = filtered_df[filtered_df["expense_date"].dt.date >= today - timedelta(days=29)]
    elif filter_period == "This year":
        filtered_df = filtered_df[filtered_df["expense_date"].dt.year == today.year]
    if sort_order == "Highest amount":
        filtered_df = filtered_df.sort_values("amount", ascending=False)
    elif sort_order == "Lowest amount":
        filtered_df = filtered_df.sort_values("amount", ascending=True)

month_expenses = df[df["expense_date"].dt.to_period("M") == pd.Period(today, freq="M")] if not df.empty else df
month_income = income_df[income_df["income_date"].dt.to_period("M") == pd.Period(today, freq="M")] if not income_df.empty else income_df
total_expenses = float(df.amount.sum()) if not df.empty else 0.0
total_income = float(income_df.amount.sum()) if not income_df.empty else 0.0
month_expense_total = float(month_expenses.amount.sum()) if not month_expenses.empty else 0.0
month_income_total = float(month_income.amount.sum()) if not month_income.empty else 0.0
budget = get_monthly_budget()
balance = total_income - total_expenses
month_balance = month_income_total - month_expense_total
progress = min(month_expense_total / budget, 1) if budget > 0 else 0

st.markdown('<div class="hero"><h1>💸 Your Money Dashboard</h1><p>Track spending, manage budgets, monitor income and understand your financial habits.</p></div>', unsafe_allow_html=True)
kpis = [("💵 Total Income", f"₹{total_income:,.2f}"), ("💸 Total Spent", f"₹{total_expenses:,.2f}"), ("📊 Current Balance", f"₹{balance:,.2f}"), ("📅 This Month", f"₹{month_expense_total:,.2f}")]
cols = st.columns(4)
for col, (label, value) in zip(cols, kpis):
    with col:
        st.markdown(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>', unsafe_allow_html=True)

if df.empty and income_df.empty:
    st.info("No financial records yet. Add your first expense or income from the sidebar.")
else:
    st.markdown('<div class="section">🎯 Monthly Budget</div>', unsafe_allow_html=True)
    st.progress(progress)
    status = "Within budget" if month_expense_total <= budget else "Budget exceeded"
    st.caption(f"{status} • ₹{month_expense_total:,.2f} of ₹{budget:,.2f} used ({progress * 100:.0f}%) • Monthly balance: ₹{month_balance:,.2f}")

    st.markdown('<div class="section">📊 Expense Analytics</div>', unsafe_allow_html=True)
    period = st.segmented_control("View by", ["Daily", "Weekly", "Monthly", "Yearly"], default="Monthly") or "Monthly"
    if not df.empty:
        chart_df = df.copy()
        if period == "Daily":
            chart_df = chart_df[chart_df.expense_date.dt.date >= today - timedelta(days=29)]
            grouped = chart_df.groupby("expense_date", as_index=False).amount.sum().sort_values("expense_date")
            grouped["Period"] = grouped.expense_date.dt.strftime("%d %b")
        elif period == "Weekly":
            chart_df["Period"] = chart_df.expense_date.dt.to_period("W").apply(lambda x: x.start_time)
            grouped = chart_df.groupby("Period", as_index=False).amount.sum().sort_values("Period")
            grouped["Period"] = grouped.Period.dt.strftime("%d %b")
        elif period == "Yearly":
            chart_df["Period"] = chart_df.expense_date.dt.year
            grouped = chart_df.groupby("Period", as_index=False).amount.sum().sort_values("Period")
            grouped["Period"] = grouped.Period.astype(str)
        else:
            chart_df["Period"] = chart_df.expense_date.dt.to_period("M").dt.to_timestamp()
            grouped = chart_df.groupby("Period", as_index=False).amount.sum().sort_values("Period")
            grouped["Period"] = grouped.Period.dt.strftime("%b %Y")

        left, right = st.columns(2)
        with left:
            fig = px.bar(grouped, x="Period", y="amount", title=f"{period} Spending", labels={"amount":"Amount (₹)","Period":"Period"}, text_auto=".2s")
            fig.update_layout(height=390, margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor=plot_bg, plot_bgcolor=plot_bg, font_color=text)
            st.plotly_chart(fig, use_container_width=True)
        with right:
            cat = df.groupby("category", as_index=False).amount.sum().sort_values("amount", ascending=False)
            fig2 = px.pie(cat, names="category", values="amount", title="Spending by Category", hole=.48)
            fig2.update_layout(height=390, margin=dict(l=10,r=10,t=55,b=10), showlegend=True, paper_bgcolor=plot_bg, plot_bgcolor=plot_bg, font_color=text, legend=dict(font=dict(color=text)))
            st.plotly_chart(fig2, use_container_width=True)

        daily = df.groupby("expense_date", as_index=False).amount.sum().sort_values("expense_date")
        fig3 = px.line(daily, x="expense_date", y="amount", markers=True, title="Daily Spending Trend", labels={"expense_date":"Date","amount":"Amount (₹)"})
        fig3.update_layout(height=330, margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor=plot_bg, plot_bgcolor=plot_bg, font_color=text)
        st.markdown('<div class="section">📈 Spending Trend</div>', unsafe_allow_html=True)
        st.plotly_chart(fig3, use_container_width=True)

    if not income_df.empty:
        st.markdown('<div class="section">💰 Income vs Expense</div>', unsafe_allow_html=True)
        inc = income_df.copy(); inc["Period"] = inc.income_date.dt.to_period("M").dt.to_timestamp()
        inc_group = inc.groupby("Period", as_index=False).amount.sum().rename(columns={"amount":"Income"})
        exp = df.copy()
        if not exp.empty:
            exp["Period"] = exp.expense_date.dt.to_period("M").dt.to_timestamp()
            exp_group = exp.groupby("Period", as_index=False).amount.sum().rename(columns={"amount":"Expense"})
        else:
            exp_group = pd.DataFrame(columns=["Period","Expense"])
        compare = pd.merge(inc_group, exp_group, on="Period", how="outer").fillna(0).sort_values("Period")
        compare_long = compare.melt(id_vars="Period", value_vars=["Income","Expense"], var_name="Type", value_name="Amount")
        compare_long["Period"] = compare_long["Period"].dt.strftime("%b %Y")
        fig4 = px.bar(compare_long, x="Period", y="Amount", color="Type", barmode="group", title="Monthly Income vs Expense")
        fig4.update_layout(height=380, margin=dict(l=10,r=10,t=55,b=10), paper_bgcolor=plot_bg, plot_bgcolor=plot_bg, font_color=text)
        st.plotly_chart(fig4, use_container_width=True)

    category_budgets = load_category_budgets()
    if category_budgets and not df.empty:
        st.markdown('<div class="section">🎯 Category Budget Progress</div>', unsafe_allow_html=True)
        budget_rows = []
        for cat_name, limit in category_budgets.items():
            spent = float(month_expenses.loc[month_expenses.category == cat_name, "amount"].sum()) if not month_expenses.empty else 0.0
            budget_rows.append({"Category":cat_name,"Spent":spent,"Budget":limit,"Remaining":max(limit-spent,0),"Used %":min(spent/limit*100,100) if limit else 0})
        budget_df = pd.DataFrame(budget_rows).sort_values("Used %", ascending=False)
        st.dataframe(budget_df, use_container_width=True, hide_index=True, column_config={"Spent":st.column_config.NumberColumn("Spent",format="₹%.2f"),"Budget":st.column_config.NumberColumn("Budget",format="₹%.2f"),"Remaining":st.column_config.NumberColumn("Remaining",format="₹%.2f"),"Used %":st.column_config.ProgressColumn("Used %",min_value=0,max_value=100,format="%.0f%%")})

    st.markdown('<div class="section">💡 Smart Insights</div>', unsafe_allow_html=True)
    cat_month = month_expenses.groupby("category").amount.sum() if not month_expenses.empty else pd.Series(dtype=float)
    top_cat = cat_month.idxmax() if not cat_month.empty else "No data"
    top_val = float(cat_month.max()) if not cat_month.empty else 0
    prev_period = today.replace(day=1) - timedelta(days=1)
    prev_start = prev_period.replace(day=1)
    prev_df = df[(df.expense_date.dt.date >= prev_start) & (df.expense_date.dt.date <= prev_period)] if not df.empty else df
    prev_total = float(prev_df.amount.sum()) if not prev_df.empty else 0
    change = ((month_expense_total-prev_total)/prev_total*100) if prev_total else None
    avg_daily = month_expense_total/today.day if month_expense_total else 0
    ins = st.columns(4)
    with ins[0]: st.markdown(f'<div class="insight">🏆 <b>Top category</b><br>{top_cat}<br><small>₹{top_val:,.2f} this month</small></div>', unsafe_allow_html=True)
    with ins[1]: st.markdown(f'<div class="insight">📅 <b>Daily average</b><br>₹{avg_daily:,.2f}<br><small>Based on this month</small></div>', unsafe_allow_html=True)
    with ins[2]:
        text_change = "No previous-month data" if change is None else (f"↑ {change:.1f}% vs last month" if change > 0 else f"↓ {abs(change):.1f}% vs last month")
        st.markdown(f'<div class="insight">🔄 <b>Monthly comparison</b><br>{text_change}<br><small>Previous: ₹{prev_total:,.2f}</small></div>', unsafe_allow_html=True)
    with ins[3]:
        savings_rate = (month_balance/month_income_total*100) if month_income_total else 0
        st.markdown(f'<div class="insight">💎 <b>Savings rate</b><br>{savings_rate:.1f}%<br><small>This month</small></div>', unsafe_allow_html=True)

st.markdown('<div class="section">🧾 Recent Transactions</div>', unsafe_allow_html=True)
st.caption(f"Showing {min(len(filtered_df),15)} of {len(filtered_df)} filtered expense records.")

if st.session_state.edit_id is not None:
    edit_row = df[df.id == st.session_state.edit_id]
    if not edit_row.empty:
        r = edit_row.iloc[0]
        st.markdown("### ✏️ Edit Expense")
        with st.form("edit_expense_form"):
            edit_date = st.date_input("Date", value=r.expense_date.date())
            edit_categories = load_categories()
            edit_category = st.selectbox("Category", edit_categories, index=edit_categories.index(r.category) if r.category in edit_categories else 0)
            edit_description = st.text_input("Description", value=r.description or "")
            edit_amount = st.number_input("Amount (₹)", min_value=0.01, value=float(r.amount), step=10.0, format="%.2f")
            ec1, ec2 = st.columns(2)
            save_edit = ec1.form_submit_button("Save Changes", type="primary", use_container_width=True)
            cancel_edit = ec2.form_submit_button("Cancel", use_container_width=True)
            if save_edit:
                update_expense(int(r.id), edit_date, str(edit_category).strip(), edit_description, edit_amount)
                st.session_state.edit_id = None
                st.rerun()
            if cancel_edit:
                st.session_state.edit_id = None
                st.rerun()

if filtered_df.empty:
    st.info("No expenses match your current filters.")
else:
    header = st.columns([1.15,1.25,2.5,1.25,.7,.7])
    for col, label in zip(header,["Date","Category","Description","Amount","Edit","Delete"]): col.markdown(f"**{label}**")
    for row in filtered_df.head(15).itertuples():
        cols = st.columns([1.15,1.25,2.5,1.25,.7,.7])
        cols[0].write(row.expense_date.strftime("%Y-%m-%d")); cols[1].write(row.category); cols[2].write(row.description or "—"); cols[3].write(f"₹{row.amount:,.2f}")
        with cols[4]:
            st.markdown('<div class="edit-btn">', unsafe_allow_html=True)
            if st.button("✏️", key=f"edit_{row.id}", help=f"Edit expense #{row.id}"):
                st.session_state.edit_id = int(row.id); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)
        with cols[5]:
            st.markdown('<div class="delete-btn">', unsafe_allow_html=True)
            if st.button("🗑️", key=f"delete_{row.id}", help=f"Delete expense #{row.id}"):
                delete_expense(int(row.id)); st.toast("Expense deleted successfully!", icon="🗑️"); st.rerun()
            st.markdown('</div>', unsafe_allow_html=True)

if not income_df.empty:
    st.markdown('<div class="section">💵 Recent Income</div>', unsafe_allow_html=True)
    ih = st.columns([1.3,1.5,3,1.4,.8])
    for col, label in zip(ih,["Date","Source","Description","Amount","Delete"]): col.markdown(f"**{label}**")
    for row in income_df.head(10).itertuples():
        cols = st.columns([1.3,1.5,3,1.4,.8])
        cols[0].write(row.income_date.strftime("%Y-%m-%d")); cols[1].write(row.source); cols[2].write(row.description or "—"); cols[3].write(f"₹{row.amount:,.2f}")
        with cols[4]:
            if st.button("🗑️", key=f"delete_income_{row.id}", help=f"Delete income #{row.id}"):
                delete_income(int(row.id)); st.toast("Income deleted successfully!", icon="🗑️"); st.rerun()

st.markdown('<div class="section">⬇️ Export Data</div>', unsafe_allow_html=True)
e1, e2 = st.columns(2)
e1.download_button("Export Expenses CSV", df.to_csv(index=False).encode("utf-8"), "expenses.csv", "text/csv", use_container_width=True)
e2.download_button("Export Income CSV", income_df.to_csv(index=False).encode("utf-8"), "income.csv", "text/csv", use_container_width=True)
st.markdown("<br><center><small>Expense Tracker • Built with Streamlit • Spend smarter 💸</small></center>", unsafe_allow_html=True)
