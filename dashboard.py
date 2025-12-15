import streamlit as st
import pandas as pd
import json
from sqlalchemy import create_engine
import plotly.express as px
from datetime import timedelta

# =========================================================
# PAGE CONFIG (IMPORTANT FOR STREAMLIT CLOUD)
# =========================================================
st.set_page_config(
    page_title="API Command Center",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ API Command Center")
st.caption("Executive monitoring of CPL API health, SLA & business impact")

# =========================================================
# PREMIUM UI CSS
# =========================================================
st.markdown("""
<style>
/* -------- API CARDS -------- */
.api-card {
    background: linear-gradient(145deg, #1c1c1c, #111);
    border: 1px solid #2a2a2a;
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 18px;
    box-shadow: 0 6px 18px rgba(0,0,0,.35);
}
.api-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: #aaa;
}
.api-title {
    font-weight: 600;
    text-transform: uppercase;
}
.api-metric {
    font-size: 34px;
    font-weight: 700;
    color: white;
}
.api-sub {
    font-size: 12px;
    color: #888;
}
.api-footer {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    margin-top: 8px;
}
.success { color: #00d084; }
.failure { color: #ff5c5c; }
.rate { color: #5dade2; }

/* -------- ALERTS -------- */
.alert-box {
    background-color: #fff5f5;
    border-left: 6px solid #ff4d4f;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 10px;
    color: #333;
}
.alert-box b { color: #b71c1c; }
.alert-rate { font-size: 13px; color: #555; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# DATABASE LOADER (CLOUD SAFE)
# =========================================================
@st.cache_data(ttl=120)
def load_data():
    try:
        host = st.secrets.get("DB_HOST")
        port = st.secrets.get("DB_PORT", "3306")
        user = st.secrets.get("DB_USER")
        pwd = st.secrets.get("DB_PASS")
        db = st.secrets.get("DB_NAME")
    except Exception:
        return pd.DataFrame()

    if not all([host, user, pwd, db]):
        return pd.DataFrame()

    try:
        engine = create_engine(
            f"mysql+pymysql://{user}:{pwd}@{host}:{port}/{db}",
            pool_pre_ping=True,
            connect_args={"connect_timeout": 5}
        )
        df = pd.read_sql(
            "SELECT * FROM cpl_api_logs ORDER BY createdAt DESC LIMIT 50000",
            engine
        )
        df["createdAt"] = pd.to_datetime(df["createdAt"])
        return df
    except Exception:
        return pd.DataFrame()

# =========================================================
# STATUS & FAILURE PARSER
# =========================================================
def enrich(df):
    def parse(row):
        try:
            resp = row["response"]
            resp = json.loads(resp) if isinstance(resp, str) else (resp or {})

            if resp.get("status") is False:
                return "Failure", str(resp.get("message", "Technical Error"))

            if row["apiName"] == "mobileDetails" and not resp.get("data"):
                return "No Data", "Customer Not Found"

            if row["apiName"] == "vehicleDetails":
                msg = resp.get("data", {}).get("data", {}).get("message")
                if msg == "No Record Found":
                    return "No Data", "Vehicle Not Found"

            return "Success", "-"
        except Exception:
            return "Failure", "JSON Parse Error"

    df[["Status", "Failure_Reason"]] = df.apply(
        parse, axis=1, result_type="expand"
    )
    return df

# =========================================================
# LOAD DATA
# =========================================================
with st.spinner("Loading API telemetry..."):
    df = load_data()

if df.empty:
    st.warning("⚠️ Data source unavailable or empty")
    st.info("Dashboard is running. Waiting for data.")
    st.stop()

df = enrich(df)

# =========================================================
# SIDEBAR CONTROLS
# =========================================================
with st.sidebar:
    st.header("🎛 Controls")
    period = st.radio("Time Window", ["Last 24 Hours", "Last 7 Days", "All Time"])

    now = df["createdAt"].max()
    start_time = {
        "Last 24 Hours": now - timedelta(hours=24),
        "Last 7 Days": now - timedelta(days=7),
        "All Time": df["createdAt"].min()
    }[period]

    df = df[df["createdAt"] >= start_time]
    st.caption(f"Records analyzed: {len(df):,}")

# =========================================================
# EXECUTIVE SUMMARY
# =========================================================
total = len(df)
success = (df["Status"] == "Success").sum()
failure = (df["Status"] == "Failure").sum()
nodata = (df["Status"] == "No Data").sum()
rate = round(success / total * 100, 1) if total else 0

health = "🟢 HEALTHY" if rate >= 97 else "🟡 DEGRADED" if rate >= 90 else "🔴 CRITICAL"

c1, c2, c3, c4 = st.columns(4)
c1.metric("System Health", health)
c2.metric("Success Rate", f"{rate}%")
c3.metric("Failures", failure)
c4.metric("No Data", nodata)

st.divider()

# =========================================================
# TABS (RESTORED STRUCTURE)
# =========================================================
tab_status, tab_alerts, tab_trends, tab_tech, tab_report = st.tabs([
    "⚡ Live Status",
    "🚨 Alerts",
    "📈 Trends & SLA",
    "🔧 Tech Drilldown",
    "📝 Report"
])

# =========================================================
# TAB 1 — LIVE STATUS (COOL CARDS)
# =========================================================
with tab_status:
    st.subheader("Live Status of All CPL Integrations")

    summary = (
        df.groupby("apiName")["Status"]
        .value_counts()
        .unstack(fill_value=0)
    )

    for col in ["Success", "Failure"]:
        if col not in summary.columns:
            summary[col] = 0

    summary["Total"] = summary.sum(axis=1)
    summary["Rate"] = (summary["Success"] / summary["Total"] * 100).round(1)
    summary = summary.sort_values("Rate")

    def api_card(api, row):
        icon = "🟢" if row["Rate"] >= 97 else "🟡" if row["Rate"] >= 90 else "🔴"
        st.markdown(f"""
        <div class="api-card">
            <div class="api-header">
                <span class="api-title">{api}</span>
                <span>{icon}</span>
            </div>
            <div class="api-metric">{int(row["Total"])}</div>
            <div class="api-sub">Requests</div>
            <div class="api-footer">
                <span class="success">{int(row["Success"])} Success</span>
                <span class="failure">{int(row["Failure"])} Failed</span>
            </div>
            <div class="api-footer">
                <span class="rate">{row["Rate"]}% Success Rate</span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    cols = st.columns(3)
    for i, (api, row) in enumerate(summary.iterrows()):
        with cols[i % 3]:
            api_card(api, row)

# =========================================================
# TAB 2 — ALERTS (READABLE)
# =========================================================
with tab_alerts:
    st.subheader("Active SLA Breaches")

    sla = (
        df.groupby("apiName")["Status"]
        .apply(lambda x: (x == "Success").mean() * 100)
    )

    breaches = sla[sla < 90]

    if breaches.empty:
        st.success("All APIs are operating within SLA 🎉")
    else:
        for api, val in breaches.items():
            st.markdown(
                f"""
                <div class="alert-box">
                    🚨 <b>{api}</b> is below SLA
                    <div class="alert-rate">Success Rate: {val:.1f}%</div>
                </div>
                """,
                unsafe_allow_html=True
            )

# =========================================================
# TAB 3 — TRENDS & SLA
# =========================================================
with tab_trends:
    st.subheader("Success Rate Trend")

    hourly = (
        df.set_index("createdAt")
        .resample("h")["Status"]
        .value_counts()
        .unstack(fill_value=0)
    )

    hourly["Total"] = hourly.sum(axis=1)
    hourly["Success Rate"] = hourly.get("Success", 0) / hourly["Total"] * 100

    fig = px.line(hourly, y="Success Rate", markers=True)
    fig.add_hline(y=95, line_dash="dot", annotation_text="Target SLA")
    fig.update_layout(yaxis_range=[0, 105])

    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# TAB 4 — TECH DRILLDOWN
# =========================================================
with tab_tech:
    st.subheader("Top Failure Reasons")

    failures = df[df["Status"] == "Failure"]

    if failures.empty:
        st.success("No failures detected 🎉")
    else:
        top = (
            failures.groupby(["apiName", "Failure_Reason"])
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
            .head(15)
        )
        st.dataframe(top, use_container_width=True)

# =========================================================
# TAB 5 — EXEC REPORT
# =========================================================
with tab_report:
    st.subheader("Executive Summary")

    report = f"""
SYSTEM STATUS: {health}
TIME WINDOW: {period}

TOTAL REQUESTS: {total}
SUCCESS RATE: {rate}%
FAILURES: {failure}
NO DATA CASES: {nodata}

ACTION POINTS:
- Investigate APIs below SLA
- Track recurring failure reasons
- Monitor business impact of No Data cases
"""

    st.text_area("Weekly Summary", report, height=240)
