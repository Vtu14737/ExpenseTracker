import streamlit as st
import sqlite3
from datetime import date, timedelta
from pathlib import Path
import pandas as pd
import plotly.express as px

st.set_page_config(page_title="Expense Tracker", page_icon="💸", layout="wide", initial_sidebar_state="expanded")

st.markdown("""
<style>
.stApp{background:#f5f7fb}.block-container{max-width:1400px;padding-top:1.8rem}
[data-testid="stSidebar"]{background:#111827}[data-testid="stSidebar"] *{color:#f9fafb!important}
.hero{background:linear-gradient(135deg,#111827,#374151);padding:28px 32px;border-radius:22px;color:white;margin-bottom:22px;box-shadow:0 10px 28px #00000014}.hero h1{margin:0;color:white}.hero p{color:#d1d5db;margin:6px 0 0}
.card{background:white;border:1px solid #e5e7eb;border-radius:18px;padding:19px;box-shadow:0 5px 18px #0f172a0b;min-height:115px}.label{font-size:.82rem;color:#6b7280;font-weight:650}.value{font-size:1.55rem;color:#111827;font-weight:750;margin-top:7px}.good{color:#15803d}.warn{color:#b45309}.bad{color:#dc2626}
.section{font-size:1.18rem;font-weight:750;color:#111827;margin:20px 0 12px}.insight{background:white;border:1px solid #e5e7eb;border-radius:16px;padding:15px 17px;height:100%}
.stButton button,.stDownloadButton button{border-radius:10px;font-weight:650}
</style>
""", unsafe_allow_html=True)

DB_PATH=Path(__file__).with_name("expenses.db")

def get_connection():
    conn=sqlite3.connect(DB_PATH,check_same_thread=False)
    conn.execute("""CREATE TABLE IF NOT EXISTS expenses(
        id INTEGER PRIMARY KEY AUTOINCREMENT, expense_date TEXT NOT NULL,
        category TEXT NOT NULL, description TEXT DEFAULT '', amount REAL NOT NULL CHECK(amount>=0))""")
    conn.commit(); return conn
conn=get_connection()

def load_expenses():
    return pd.read_sql_query("SELECT id,expense_date,category,description,amount FROM expenses ORDER BY expense_date DESC,id DESC",conn)

with st.sidebar:
    st.markdown("# 💸 Expense Tracker")
    st.caption("Personal finance dashboard")
    st.divider(); st.markdown("### ➕ Add Expense")
    with st.form("expense_form",clear_on_submit=True):
        expense_date=st.date_input("Date",value=date.today())
        category=st.selectbox("Category",["Food","Travel","Shopping","Bills","Health","Entertainment","Education","Other"])
        description=st.text_input("Description",placeholder="Lunch, fuel, electricity...")
        amount=st.number_input("Amount (₹)",min_value=0.01,step=10.0,format="%.2f")
        if st.form_submit_button("Add Expense  →",use_container_width=True,type="primary"):
            conn.execute("INSERT INTO expenses(expense_date,category,description,amount) VALUES(?,?,?,?)",(expense_date.isoformat(),category,description.strip(),amount)); conn.commit(); st.success("Expense added!"); st.rerun()
    st.divider(); st.markdown("### 🎯 Monthly Budget")
    budget=st.number_input("Budget (₹)",min_value=0.0,value=float(st.session_state.get("budget",20000.0)),step=1000.0)
    st.session_state["budget"]=budget
    st.caption("Set your target monthly spending limit.")

df=load_expenses()

today=date.today()
total=float(df.amount.sum()) if not df.empty else 0
month_start=today.replace(day=1)
month_df=df[pd.to_datetime(df.expense_date).dt.to_period("M")==pd.Period(today, freq="M")] if not df.empty else df
month_total=float(month_df.amount.sum()) if not month_df.empty else 0
remaining=max(budget-month_total,0)
progress=min(month_total/budget,1) if budget>0 else 0

st.markdown('<div class="hero"><h1>💸 Your Money Dashboard</h1><p>Track spending, understand habits and stay within your budget.</p></div>',unsafe_allow_html=True)

c=st.columns(4)
for col,label,value in zip(c,["💰 Total Spent","📅 This Month","🎯 Budget Left","🧾 Transactions"],[f"₹{total:,.2f}",f"₹{month_total:,.2f}",f"₹{remaining:,.2f}",f"{len(df):,}"]):
    with col: st.markdown(f'<div class="card"><div class="label">{label}</div><div class="value">{value}</div></div>',unsafe_allow_html=True)

if df.empty:
    st.info("No expenses yet. Add your first expense from the sidebar."); st.stop()

st.markdown('<div class="section">🎯 Monthly Budget</div>',unsafe_allow_html=True)
st.progress(progress)
status="Within budget" if month_total<=budget else "Budget exceeded"
st.caption(f"{status} • ₹{month_total:,.2f} of ₹{budget:,.2f} used ({progress*100:.0f}%)")

st.markdown('<div class="section">📊 Expense Analytics</div>',unsafe_allow_html=True)
period=st.segmented_control("View by",["Daily","Weekly","Monthly","Yearly"],default="Monthly")
if period is None: period="Monthly"

chart_df=df.copy(); chart_df["expense_date"]=pd.to_datetime(chart_df["expense_date"])
if period=="Daily":
    start=today-timedelta(days=29); chart_df=chart_df[chart_df.expense_date.dt.date>=start]; chart_df["Period"]=chart_df.expense_date.dt.strftime("%d %b")
    grouped=chart_df.groupby("expense_date",as_index=False).amount.sum().sort_values("expense_date"); grouped["Period"]=grouped.expense_date.dt.strftime("%d %b")
elif period=="Weekly":
    chart_df["Period"]=chart_df.expense_date.dt.to_period("W").apply(lambda x:x.start_time); grouped=chart_df.groupby("Period",as_index=False).amount.sum().sort_values("Period"); grouped["Period"]=grouped.Period.dt.strftime("%d %b")
elif period=="Yearly":
    chart_df["Period"]=chart_df.expense_date.dt.year; grouped=chart_df.groupby("Period",as_index=False).amount.sum().sort_values("Period"); grouped["Period"]=grouped.Period.astype(str)
else:
    chart_df["Period"]=chart_df.expense_date.dt.to_period("M").dt.to_timestamp(); grouped=chart_df.groupby("Period",as_index=False).amount.sum().sort_values("Period"); grouped["Period"]=grouped.Period.dt.strftime("%b %Y")

left,right=st.columns(2)
with left:
    fig=px.bar(grouped,x="Period",y="amount",title=f"{period} Spending",labels={"amount":"Amount (₹)","Period":"Period"},text_auto=".2s")
    fig.update_layout(height=390,margin=dict(l=10,r=10,t=55,b=10),paper_bgcolor="white",plot_bgcolor="white")
    st.plotly_chart(fig,use_container_width=True)
with right:
    cat=df.groupby("category",as_index=False).amount.sum().sort_values("amount",ascending=False)
    fig2=px.pie(cat,names="category",values="amount",title="Spending by Category",hole=.48)
    fig2.update_layout(height=390,margin=dict(l=10,r=10,t=55,b=10),showlegend=True)
    st.plotly_chart(fig2,use_container_width=True)

# Trend and insights
st.markdown('<div class="section">📈 Spending Trend</div>',unsafe_allow_html=True)
daily=df.copy(); daily["expense_date"]=pd.to_datetime(daily.expense_date); daily=daily.groupby("expense_date",as_index=False).amount.sum().sort_values("expense_date")
fig3=px.line(daily,x="expense_date",y="amount",markers=True,title="Daily Spending Trend",labels={"expense_date":"Date","amount":"Amount (₹)"})
fig3.update_layout(height=330,margin=dict(l=10,r=10,t=55,b=10),paper_bgcolor="white",plot_bgcolor="white")
st.plotly_chart(fig3,use_container_width=True)

st.markdown('<div class="section">💡 Smart Insights</div>',unsafe_allow_html=True)
cat_month=month_df.groupby("category").amount.sum() if not month_df.empty else pd.Series(dtype=float)
top_cat=cat_month.idxmax() if not cat_month.empty else "No data"
top_val=float(cat_month.max()) if not cat_month.empty else 0
prev_period=today.replace(day=1)-timedelta(days=1); prev_start=prev_period.replace(day=1)
prev_df=df[(pd.to_datetime(df.expense_date).dt.date>=prev_start)&(pd.to_datetime(df.expense_date).dt.date<=prev_period)]
prev_total=float(prev_df.amount.sum()) if not prev_df.empty else 0
change=((month_total-prev_total)/prev_total*100) if prev_total else None
avg_daily=month_total/today.day if month_total else 0
ins=st.columns(3)
with ins[0]: st.markdown(f'<div class="insight">🏆 <b>Top category</b><br>{top_cat}<br><small>₹{top_val:,.2f} this month</small></div>',unsafe_allow_html=True)
with ins[1]: st.markdown(f'<div class="insight">📅 <b>Daily average</b><br>₹{avg_daily:,.2f}<br><small>Based on this month</small></div>',unsafe_allow_html=True)
with ins[2]:
    text="No previous-month data" if change is None else (f"↑ {change:.1f}% vs last month" if change>0 else f"↓ {abs(change):.1f}% vs last month")
    st.markdown(f'<div class="insight">🔄 <b>Monthly comparison</b><br>{text}<br><small>Previous: ₹{prev_total:,.2f}</small></div>',unsafe_allow_html=True)

st.markdown('<div class="section">🧾 Recent Transactions</div>',unsafe_allow_html=True)
display=df.head(15).copy(); display["amount"]=display.amount.map(lambda x:f"₹{x:,.2f}"); display=display.rename(columns={"expense_date":"Date","category":"Category","description":"Description","amount":"Amount"})
st.dataframe(display[["Date","Category","Description","Amount"]],use_container_width=True,hide_index=True,height=380)
st.download_button("⬇️ Export CSV",df.to_csv(index=False).encode("utf-8"),"expenses.csv","text/csv")

with st.expander("⚙️ Manage Expenses"):
    options={f"#{r.id} • {r.expense_date} • {r.category} • ₹{r.amount:,.2f}":int(r.id) for r in df.itertuples()}
    selected=st.selectbox("Select transaction to delete",list(options))
    if st.button("Delete Selected Expense"):
        conn.execute("DELETE FROM expenses WHERE id=?",(options[selected],)); conn.commit(); st.success("Expense deleted."); st.rerun()

st.markdown("<br><center><small>Expense Tracker • Built with Streamlit • Spend smarter 💸</small></center>",unsafe_allow_html=True)
