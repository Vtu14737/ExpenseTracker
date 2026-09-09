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

# -----------------------------------------------------------------------------
# Authentication
# -----------------------------------------------------------------------------
AUTH_CONFIGURED = "auth" in st.secrets

if not AUTH_CONFIGURED:
    st.title("💸 Expense Tracker")
    st.warning("Google authentication is not configured yet.")
    st.markdown("""
    Add an `[auth]` section to Streamlit Cloud Secrets with your Google OAuth
    Client ID, Client Secret, redirect URI, cookie secret, and the Google OIDC
    discovery URL. The database connection can remain under `[connections.neon]`.
    """)
    st.code('''[auth]\nredirect_uri = "https://YOUR-APP.streamlit.app/oauth2callback"\ncookie_secret = "YOUR_RANDOM_SECRET"\nclient_id = "YOUR_GOOGLE_CLIENT_ID"\nclient_secret = "YOUR_GOOGLE_CLIENT_SECRET"\nserver_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"\n\n[app]\nallowed_emails = ["your-email@gmail.com"]''', language="toml")
    st.info("After saving Secrets, reload the app and use the Log in with Google button.")
    st.stop()

if not st.user.is_logged_in:
    st.markdown("# 💸 Expense Tracker")
    st.subheader("Your personal finance dashboard")
    st.write("Sign in with Google to keep your financial data private to your account.")
    st.button("🔵 Log in with Google", on_click=st.login, type="primary")
    st.stop()

USER_EMAIL = str(getattr(st.user, "email", "") or "").strip().lower()
USER_NAME = str(getattr(st.user, "name", "") or USER_EMAIL or "User")

if not USER_EMAIL:
    st.error("Google did not provide an email address. Please sign out and try again.")
    st.stop()

allowed_emails = []
try:
    allowed_emails = [str(x).strip().lower() for x in st.secrets.get("app", {}).get("allowed_emails", []) if str(x).strip()]
except Exception:
    allowed_emails = []

if allowed_emails and USER_EMAIL not in allowed_emails:
    st.title("🔒 Access restricted")
    st.error("Your Google account is authenticated, but it is not on the approved user list.")
    st.write("Ask the app administrator to add your email address to the `allowed_emails` list in Streamlit Secrets.")
    st.button("Log out", on_click=st.logout)
    st.stop()

# -----------------------------------------------------------------------------
# Database connection
# -----------------------------------------------------------------------------
cloud_conn = None
try:
    if "connections" in st.secrets and "neon" in st.secrets["connections"]:
        cloud_conn = st.connection("neon", type="sql")
except Exception as exc:
    st.error("Could not initialize the Neon database connection.")
    st.caption(f"Check Streamlit Secrets and the Neon connection string. Error type: {type(exc).__name__}")
    st.stop()

using_cloud_db = cloud_conn is not None


def sqlite_connection():
    return sqlite3.connect(DB_PATH, check_same_thread=False)


local_conn = None if using_cloud_db else sqlite_connection()


def init_cloud_db():
    statements = [
        """CREATE TABLE IF NOT EXISTS users(
            email TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)""",
        """CREATE TABLE IF NOT EXISTS expenses(
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            expense_date DATE NOT NULL,
            category TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0))""",
        """CREATE TABLE IF NOT EXISTS categories(
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            name TEXT NOT NULL)""",
        """CREATE TABLE IF NOT EXISTS income(
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            income_date DATE NOT NULL,
            source TEXT NOT NULL,
            description TEXT DEFAULT '',
            amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0))""",
        """CREATE TABLE IF NOT EXISTS category_budgets(
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            category TEXT NOT NULL,
            amount NUMERIC(12,2) NOT NULL CHECK(amount >= 0))""",
        """CREATE TABLE IF NOT EXISTS app_settings(
            id SERIAL PRIMARY KEY,
            user_email TEXT,
            setting_key TEXT NOT NULL,
            setting_value TEXT NOT NULL)""",
    ]
    with cloud_conn.session as session:
        for sql in statements:
            session.execute(text(sql))
        # Add user_email to databases created by the previous single-user version.
        for table in ["expenses", "categories", "income", "category_budgets", "app_settings"]:
            session.execute(text(f'ALTER TABLE {table} ADD COLUMN IF NOT EXISTS user_email TEXT'))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_expenses_user ON expenses(user_email)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_income_user ON income(user_email)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_categories_user ON categories(user_email)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_budgets_user ON category_budgets(user_email)"))
        session.execute(text("CREATE INDEX IF NOT EXISTS idx_settings_user ON app_settings(user_email)"))
        session.execute(text("INSERT INTO users(email,name) VALUES(:e,:n) ON CONFLICT(email) DO UPDATE SET name=EXCLUDED.name"), {"e": USER_EMAIL, "n": USER_NAME})
        # One-time compatibility migration: old shared records are assigned to the first authenticated user.
        for table in ["expenses", "categories", "income", "category_budgets", "app_settings"]:
            session.execute(text(f"UPDATE {table} SET user_email=:e WHERE user_email IS NULL OR user_email=''"), {"e": USER_EMAIL})
        for item in DEFAULT_CATEGORIES:
            session.execute(text("INSERT INTO categories(user_email,name) SELECT :e,:n WHERE NOT EXISTS (SELECT 1 FROM categories WHERE user_email=:e AND name=:n)"), {"e": USER_EMAIL, "n": item})
        session.commit()


def init_sqlite_db():
    local_conn.execute("""CREATE TABLE IF NOT EXISTS users(email TEXT PRIMARY KEY, name TEXT NOT NULL, created_at TEXT DEFAULT CURRENT_TIMESTAMP)""")
    local_conn.execute("""CREATE TABLE IF NOT EXISTS expenses(id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, expense_date TEXT NOT NULL, category TEXT NOT NULL, description TEXT DEFAULT '', amount REAL NOT NULL CHECK(amount >= 0))""")
    local_conn.execute("""CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, name TEXT NOT NULL)""")
    local_conn.execute("""CREATE TABLE IF NOT EXISTS income(id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, income_date TEXT NOT NULL, source TEXT NOT NULL, description TEXT DEFAULT '', amount REAL NOT NULL CHECK(amount >= 0))""")
    local_conn.execute("""CREATE TABLE IF NOT EXISTS category_budgets(id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, category TEXT NOT NULL, amount REAL NOT NULL CHECK(amount >= 0))""")
    local_conn.execute("""CREATE TABLE IF NOT EXISTS app_settings(id INTEGER PRIMARY KEY AUTOINCREMENT, user_email TEXT, setting_key TEXT NOT NULL, setting_value TEXT NOT NULL)""")
    local_conn.execute("INSERT OR REPLACE INTO users(email,name) VALUES(?,?)", (USER_EMAIL, USER_NAME))
    for table in ["expenses", "categories", "income", "category_budgets", "app_settings"]:
        try:
            local_conn.execute(f"UPDATE {table} SET user_email=? WHERE user_email IS NULL OR user_email=''", (USER_EMAIL,))
        except Exception:
            pass
    for item in DEFAULT_CATEGORIES:
        if local_conn.execute("SELECT 1 FROM categories WHERE user_email=? AND name=?", (USER_EMAIL, item)).fetchone() is None:
            local_conn.execute("INSERT INTO categories(user_email,name) VALUES(?,?)", (USER_EMAIL, item))
    local_conn.commit()


if using_cloud_db:
    init_cloud_db()
else:
    init_sqlite_db()


def query_df(sql, params=None):
    params = params or {}
    if using_cloud_db:
        return cloud_conn.query(sql, params=params, ttl=0)
    return pd.read_sql_query(sql, local_conn, params=params)


def execute(sql, params=None):
    params = params or {}
    if using_cloud_db:
        with cloud_conn.session as session:
            session.execute(text(sql), params)
            session.commit()
    else:
        local_conn.execute(sql, tuple(params.values()) if isinstance(params, dict) else params)
        local_conn.commit()


def load_expenses():
    return query_df("SELECT id, expense_date, category, description, amount FROM expenses WHERE user_email=:u ORDER BY expense_date DESC, id DESC", {"u": USER_EMAIL})


def load_income():
    return query_df("SELECT id, income_date, source, description, amount FROM income WHERE user_email=:u ORDER BY income_date DESC, id DESC", {"u": USER_EMAIL})


def load_categories():
    df = query_df("SELECT name FROM categories WHERE user_email=:u ORDER BY id", {"u": USER_EMAIL})
    return df["name"].tolist() if not df.empty else DEFAULT_CATEGORIES


def load_category_budgets():
    df = query_df("SELECT category, amount FROM category_budgets WHERE user_email=:u ORDER BY category", {"u": USER_EMAIL})
    return {r.category: float(r.amount) for r in df.itertuples()} if not df.empty else {}


def get_monthly_budget():
    df = query_df("SELECT setting_value FROM app_settings WHERE user_email=:u AND setting_key='monthly_budget' ORDER BY id DESC LIMIT 1", {"u": USER_EMAIL})
    return float(df.iloc[0, 0]) if not df.empty else 20000.0


def save_monthly_budget(amount):
    if using_cloud_db:
        execute("INSERT INTO app_settings(user_email,setting_key,setting_value) VALUES(:u,'monthly_budget',:v)", {"u": USER_EMAIL, "v": str(amount)})
    else:
        execute("INSERT INTO app_settings(user_email,setting_key,setting_value) VALUES(?,?,?)", {"a": USER_EMAIL, "b": "monthly_budget", "c": str(amount)})


def add_expense(expense_date, category, description, amount):
    if using_cloud_db:
        execute("INSERT INTO categories(user_email,name) SELECT :u,:c WHERE NOT EXISTS (SELECT 1 FROM categories WHERE user_email=:u AND name=:c)", {"u": USER_EMAIL, "c": category})
        execute("INSERT INTO expenses(user_email,expense_date,category,description,amount) VALUES(:u,:d,:c,:x,:a)", {"u": USER_EMAIL, "d": expense_date.isoformat(), "c": category, "x": description.strip(), "a": amount})
    else:
        local_conn.execute("INSERT OR IGNORE INTO categories(user_email,name) VALUES(?,?)", (USER_EMAIL, category))
        local_conn.execute("INSERT INTO expenses(user_email,expense_date,category,description,amount) VALUES(?,?,?,?,?)", (USER_EMAIL, expense_date.isoformat(), category, description.strip(), amount))
        local_conn.commit()


def add_income(income_date, source, description, amount):
    if using_cloud_db:
        execute("INSERT INTO income(user_email,income_date,source,description,amount) VALUES(:u,:d,:s,:x,:a)", {"u": USER_EMAIL, "d": income_date.isoformat(), "s": source, "x": description.strip(), "a": amount})
    else:
        local_conn.execute("INSERT INTO income(user_email,income_date,source,description,amount) VALUES(?,?,?,?,?)", (USER_EMAIL, income_date.isoformat(), source, description.strip(), amount)); local_conn.commit()


def delete_expense(expense_id):
    execute("DELETE FROM expenses WHERE id=:id AND user_email=:u" if using_cloud_db else "DELETE FROM expenses WHERE id=? AND user_email=?", {"id": expense_id, "u": USER_EMAIL})


def delete_income(income_id):
    execute("DELETE FROM income WHERE id=:id AND user_email=:u" if using_cloud_db else "DELETE FROM income WHERE id=? AND user_email=?", {"id": income_id, "u": USER_EMAIL})


def update_expense(expense_id, expense_date, category, description, amount):
    if using_cloud_db:
        execute("INSERT INTO categories(user_email,name) SELECT :u,:c WHERE NOT EXISTS (SELECT 1 FROM categories WHERE user_email=:u AND name=:c)", {"u": USER_EMAIL, "c": category})
        execute("UPDATE expenses SET expense_date=:d,category=:c,description=:x,amount=:a WHERE id=:id AND user_email=:u", {"d": expense_date.isoformat(), "c": category, "x": description.strip(), "a": amount, "id": expense_id, "u": USER_EMAIL})
    else:
        local_conn.execute("UPDATE expenses SET expense_date=?,category=?,description=?,amount=? WHERE id=? AND user_email=?", (expense_date.isoformat(), category, description.strip(), amount, expense_id, USER_EMAIL)); local_conn.commit()


def save_category_budget(category, amount):
    if using_cloud_db:
        execute("DELETE FROM category_budgets WHERE user_email=:u AND category=:c", {"u": USER_EMAIL, "c": category})
        if amount > 0:
            execute("INSERT INTO category_budgets(user_email,category,amount) VALUES(:u,:c,:a)", {"u": USER_EMAIL, "c": category, "a": amount})
    else:
        local_conn.execute("DELETE FROM category_budgets WHERE user_email=? AND category=?", (USER_EMAIL, category))
        if amount > 0:
            local_conn.execute("INSERT INTO category_budgets(user_email,category,amount) VALUES(?,?,?)", (USER_EMAIL, category, amount))
        local_conn.commit()


# -----------------------------------------------------------------------------
# UI state and styling
# -----------------------------------------------------------------------------
if "dark_mode" not in st.session_state:
    st.session_state.dark_mode = False
if "edit_id" not in st.session_state:
    st.session_state.edit_id = None

dark = st.session_state.dark_mode
if dark:
    app_bg, card_bg, text_color, muted, border, input_bg = "#0b1120", "#111827", "#f9fafb", "#cbd5e1", "#374151", "#1f2937"
else:
    app_bg, card_bg, text_color, muted, border, input_bg = "#f5f7fb", "#ffffff", "#111827", "#4b5563", "#e5e7eb", "#ffffff"

st.markdown(f"""
<style>
.stApp,[data-testid="stAppViewContainer"]{{background:{app_bg}!important;color:{text_color}!important}}
.block-container{{max-width:1450px;padding-top:1.6rem}}
.main *,section.main,section.main p,section.main span,section.main label,section.main h1,section.main h2,section.main h3,section.main h4,section.main h5,section.main h6,section.main [data-testid="stMarkdownContainer"]{{color:{text_color}}}
.main .stCaption,section.main [data-testid="stCaptionContainer"]{{color:{muted}!important}}
[data-testid="stSidebar"]{{background:#111827!important}} [data-testid="stSidebar"] *{{color:#f9fafb!important}}
section.main input,section.main textarea{{background:{input_bg}!important;color:{text_color}!important;caret-color:{text_color}!important}}
section.main input::placeholder,section.main textarea::placeholder{{color:{muted}!important;opacity:1!important}}
section.main [data-baseweb="select"]>div,section.main [data-baseweb="input"]>div,section.main [data-baseweb="textarea"]>div{{background:{input_bg}!important;color:{text_color}!important;border-color:{border}!important}}
section.main [data-baseweb="select"] *,section.main [data-baseweb="input"] *,section.main [data-baseweb="textarea"] *{{color:{text_color}!important}}
.hero{{background:linear-gradient(135deg,#111827,#4f46e5);padding:30px 34px;border-radius:24px;color:white;margin-bottom:22px;box-shadow:0 12px 30px #00000018}} .hero h1,.hero p{{color:white!important}} .hero h1{{margin:0;font-size:2rem}} .hero p{{margin:7px 0 0;color:#e5e7eb!important}}
.card{{background:{card_bg};border:1px solid {border};border-radius:18px;padding:19px;box-shadow:0 5px 18px #0f172a18;min-height:115px}} .label{{font-size:.82rem;color:{muted}!important;font-weight:650}} .value{{font-size:1.55rem;color:{text_color}!important;font-weight:750;margin-top:7px}} .section{{font-size:1.18rem;font-weight:750;color:{text_color}!important;margin:22px 0 12px}}
.stButton button,.stDownloadButton button,[data-testid="stFormSubmitButton"] button{{border-radius:12px!important;font-weight:700!important;min-height:42px!important;transition:all .18s ease!important;box-shadow:0 4px 12px rgba(15,23,42,.10)!important;border:1px solid rgba(148,163,184,.35)!important;cursor:pointer!important}}
.stButton button:hover,.stDownloadButton button:hover,[data-testid="stFormSubmitButton"] button:hover{{transform:translateY(-2px)!important;box-shadow:0 8px 20px rgba(15,23,42,.18)!important;border-color:#6366f1!important}}
</style>
""", unsafe_allow_html=True)

with st.sidebar:
    st.markdown("# 💸 Expense Tracker")
    st.caption(f"Signed in as {USER_EMAIL}")
    if using_cloud_db:
        st.success("☁️ Cloud database connected", icon="☁️")
    else:
        st.warning("💾 Local database mode", icon="⚠️")
    st.divider()
    st.toggle("🌙 Dark mode", key="dark_mode")
    if st.button("🚪 Log out", use_container_width=True):
        st.logout()
    st.divider()
    st.markdown("### ➕ Add Expense")
    categories = load_categories()
    with st.form("expense_form", clear_on_submit=True):
        expense_date = st.date_input("Date", value=date.today(), key="expense_date")
        category = st.selectbox("Category", categories, key="expense_category")
        new_category = st.text_input("Custom category (optional)", key="new_category")
        description = st.text_input("Description", key="expense_description")
        amount = st.number_input("Amount", min_value=0.0, step=10.0, format="%.2f", key="expense_amount")
        submitted = st.form_submit_button("Add Expense", type="primary", use_container_width=True)
        if submitted:
            final_category = new_category.strip() or category
            if amount <= 0:
                st.error("Enter an amount greater than 0.")
            else:
                add_expense(expense_date, final_category, description, amount)
                st.success("Expense added.")
                st.rerun()

    st.markdown("### 💰 Add Income")
    with st.form("income_form", clear_on_submit=True):
        income_date = st.date_input("Income date", value=date.today())
        source = st.text_input("Source", placeholder="Salary, freelance, etc.")
        income_desc = st.text_input("Description")
        income_amount = st.number_input("Income amount", min_value=0.0, step=100.0, format="%.2f")
        income_submitted = st.form_submit_button("Add Income", type="primary", use_container_width=True)
        if income_submitted:
            if not source.strip() or income_amount <= 0:
                st.error("Enter a source and amount greater than 0.")
            else:
                add_income(income_date, source, income_desc, income_amount)
                st.success("Income added.")
                st.rerun()

# -----------------------------------------------------------------------------
# Data and dashboard
# -----------------------------------------------------------------------------
expenses = load_expenses()
income = load_income()
budgets = load_category_budgets()
monthly_budget = get_monthly_budget()

st.markdown(f'<div class="hero"><h1>Welcome, {USER_NAME} 👋</h1><p>Track your income, expenses, budgets and savings in one place.</p></div>', unsafe_allow_html=True)

if not expenses.empty:
    expenses["expense_date"] = pd.to_datetime(expenses["expense_date"])
    expenses["amount"] = pd.to_numeric(expenses["amount"], errors="coerce").fillna(0)
if not income.empty:
    income["income_date"] = pd.to_datetime(income["income_date"])
    income["amount"] = pd.to_numeric(income["amount"], errors="coerce").fillna(0)

month_start = pd.Timestamp(date.today().replace(day=1))
month_exp = expenses[expenses["expense_date"] >= month_start] if not expenses.empty else expenses
month_inc = income[income["income_date"] >= month_start] if not income.empty else income
month_exp_total = float(month_exp["amount"].sum()) if not month_exp.empty else 0.0
month_inc_total = float(month_inc["amount"].sum()) if not month_inc.empty else 0.0
balance = month_inc_total - month_exp_total
savings_rate = (balance / month_inc_total * 100) if month_inc_total else 0.0

c1, c2, c3, c4 = st.columns(4)
for col, label, value in [
    (c1, "This month income", f"₹{month_inc_total:,.2f}"),
    (c2, "This month expenses", f"₹{month_exp_total:,.2f}"),
    (c3, "Balance", f"₹{balance:,.2f}"),
    (c4, "Savings rate", f"{savings_rate:.1f}%"),
]:
    with col:
        st.markdown(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>', unsafe_allow_html=True)

st.markdown('<div class="section">📊 Analytics</div>', unsafe_allow_html=True)
t1, t2, t3, t4 = st.tabs(["Overview", "Transactions", "Budgets", "Data"])

with t1:
    a, b = st.columns(2)
    with a:
        if not expenses.empty:
            cat = expenses.groupby("category", as_index=False)["amount"].sum().sort_values("amount", ascending=False)
            fig = px.pie(cat, names="category", values="amount", title="Expense by category", hole=.45)
            fig.update_layout(margin=dict(l=10,r=10,t=50,b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Add an expense to see category analytics.")
    with b:
        if not expenses.empty or not income.empty:
            e = expenses.groupby(expenses["expense_date"].dt.to_period("M").astype(str))["amount"].sum().rename("Expenses") if not expenses.empty else pd.Series(dtype=float)
            i = income.groupby(income["income_date"].dt.to_period("M").astype(str))["amount"].sum().rename("Income") if not income.empty else pd.Series(dtype=float)
            trend = pd.concat([i, e], axis=1).fillna(0).reset_index().rename(columns={"index":"Month"})
            trend = trend.melt(id_vars="Month", var_name="Type", value_name="Amount")
            fig = px.bar(trend, x="Month", y="Amount", color="Type", barmode="group", title="Monthly income vs expenses")
            fig.update_layout(margin=dict(l=10,r=10,t=50,b=10))
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Add income or expenses to see trends.")

with t2:
    search = st.text_input("🔎 Search transactions", placeholder="Search description, category or source")
    period = st.selectbox("Period", ["All time", "This month", "Last 30 days", "This year"])
    filtered_exp = expenses.copy()
    if period == "This month" and not filtered_exp.empty:
        filtered_exp = filtered_exp[filtered_exp["expense_date"] >= month_start]
    elif period == "Last 30 days" and not filtered_exp.empty:
        filtered_exp = filtered_exp[filtered_exp["expense_date"] >= pd.Timestamp(date.today() - timedelta(days=30))]
    elif period == "This year" and not filtered_exp.empty:
        filtered_exp = filtered_exp[filtered_exp["expense_date"].dt.year == date.today().year]
    if search and not filtered_exp.empty:
        s = search.lower()
        filtered_exp = filtered_exp[filtered_exp.apply(lambda r: s in f"{r['category']} {r['description']}".lower(), axis=1)]

    if not filtered_exp.empty:
        st.dataframe(filtered_exp[["id","expense_date","category","description","amount"]], use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export expenses CSV", filtered_exp.to_csv(index=False).encode("utf-8"), "expenses.csv", "text/csv")
        st.markdown("#### Manage expenses")
        for row in filtered_exp.head(20).itertuples():
            cols = st.columns([2,2,4,2,1,1])
            cols[0].write(row.expense_date.strftime("%d-%m-%Y"))
            cols[1].write(row.category)
            cols[2].write(row.description or "-")
            cols[3].write(f"₹{float(row.amount):,.2f}")
            if cols[4].button("✏️", key=f"edit_{row.id}"):
                st.session_state.edit_id = int(row.id)
                st.rerun()
            if cols[5].button("🗑️", key=f"del_{row.id}"):
                delete_expense(int(row.id))
                st.rerun()

        if st.session_state.edit_id:
            edit_row = filtered_exp[filtered_exp["id"] == st.session_state.edit_id]
            if not edit_row.empty:
                r = edit_row.iloc[0]
                st.markdown("#### Edit expense")
                with st.form("edit_expense_form"):
                    edate = st.date_input("Date", value=r["expense_date"].date())
                    cats = load_categories()
                    current_cat = r["category"] if r["category"] in cats else cats[0]
                    ecat = st.selectbox("Category", cats, index=cats.index(current_cat))
                    edesc = st.text_input("Description", value=str(r["description"] or ""))
                    eamt = st.number_input("Amount", min_value=0.0, value=float(r["amount"]), step=10.0)
                    x1, x2 = st.columns(2)
                    if x1.form_submit_button("Save changes", type="primary"):
                        update_expense(int(r["id"]), edate, ecat, edesc, eamt)
                        st.session_state.edit_id = None
                        st.rerun()
                    if x2.form_submit_button("Cancel"):
                        st.session_state.edit_id = None
                        st.rerun()
    else:
        st.info("No matching expenses.")

    st.markdown("#### Income")
    if not income.empty:
        st.dataframe(income[["id","income_date","source","description","amount"]], use_container_width=True, hide_index=True)
        st.download_button("⬇️ Export income CSV", income.to_csv(index=False).encode("utf-8"), "income.csv", "text/csv")
        for row in income.head(20).itertuples():
            cols = st.columns([2,3,4,2,1])
            cols[0].write(row.income_date.strftime("%d-%m-%Y"))
            cols[1].write(row.source)
            cols[2].write(row.description or "-")
            cols[3].write(f"₹{float(row.amount):,.2f}")
            if cols[4].button("🗑️", key=f"del_income_{row.id}"):
                delete_income(int(row.id)); st.rerun()
    else:
        st.info("No income recorded yet.")

with t3:
    st.markdown("#### Monthly budget")
    new_monthly = st.number_input("Monthly budget", min_value=0.0, value=float(monthly_budget), step=500.0)
    if st.button("Save monthly budget", type="primary"):
        save_monthly_budget(new_monthly); st.success("Monthly budget saved."); st.rerun()
    used_pct = (month_exp_total / new_monthly * 100) if new_monthly else 0
    st.progress(min(used_pct / 100, 1.0), text=f"₹{month_exp_total:,.2f} / ₹{new_monthly:,.2f} ({used_pct:.1f}%)")

    st.markdown("#### Category budgets")
    cats = load_categories()
    for cat in cats:
        current = float(budgets.get(cat, 0))
        cols = st.columns([3,2,1])
        cols[0].write(cat)
        val = cols[1].number_input("Budget", min_value=0.0, value=current, step=100.0, key=f"budget_{cat}", label_visibility="collapsed")
        if cols[2].button("Save", key=f"save_budget_{cat}"):
            save_category_budget(cat, val); st.rerun()

    if budgets and not expenses.empty:
        current_month = expenses[expenses["expense_date"] >= month_start]
        spent = current_month.groupby("category")["amount"].sum().to_dict() if not current_month.empty else {}
        budget_rows = []
        for cat, limit in budgets.items():
            used = float(spent.get(cat, 0))
            budget_rows.append({"Category": cat, "Budget": limit, "Spent": used, "Remaining": limit-used, "Status": "Over budget" if used > limit else "On track"})
        st.dataframe(pd.DataFrame(budget_rows), use_container_width=True, hide_index=True)

with t4:
    st.markdown("#### Your database data")
    st.caption("Only records belonging to your signed-in Google account are shown here.")
    st.write(f"**User:** {USER_EMAIL}")
    st.write(f"**Storage:** {'Neon PostgreSQL' if using_cloud_db else 'Local SQLite'}")
    st.download_button("⬇️ Export all expenses", expenses.to_csv(index=False).encode("utf-8") if not expenses.empty else b"", "all_expenses.csv", "text/csv")
    st.download_button("⬇️ Export all income", income.to_csv(index=False).encode("utf-8") if not income.empty else b"", "all_income.csv", "text/csv")

st.caption("🔐 Your records are filtered by your authenticated Google email.")
