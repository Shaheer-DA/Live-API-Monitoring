import streamlit as st
import pandas as pd
import json
from sqlalchemy import create_engine
import plotly.express as px
from datetime import timedelta, datetime
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.pagesizes import A4
import io

# =========================================================
# PAGE CONFIG
# =========================================================
st.set_page_config(
    page_title="API Command Center",
    page_icon="⚡",
    layout="wide"
)

st.title("⚡ API Command Center")
st.caption("Executive monitoring of CPL API health, SLA & business impact")

# =========================================================
# CSS
# =========================================================
st.markdown("""
<style>
.api-card {
    background: linear-gradient(145deg, #1c1c1c, #111);
    border: 1px solid #2a2a2a;
    border-radius: 14px;
    padding: 18px;
    margin-bottom: 18px;
}
.api-header {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    color: #aaa;
}
.api-title { font-weight: 600; text-transform: uppercase; }
.api-metric { font-size: 34px; font-weight: 700; color: white; }
.api-sub { font-size: 12px; color: #888; }
.api-footer {
    display: flex;
    justify-content: space-between;
    font-size: 12px;
    margin-top: 8px;
}
.success { color: #00d084; }
.failure { color: #ff5c5c; }
.rate { color: #5dade2; }

.alert-box {
    background-color: #fff5f5;
    border-left: 6px solid #ff4d4f;
    padding: 12px 16px;
    border-radius: 6px;
    margin-bottom: 10px;
}
.alert-box b { color: #b71c1c; }
</style>
""", unsafe_allow_html=True)

# =========================================================
# DB LOAD (CLOUD SAFE)
# =========================================================
@st.cache_data(ttl=120)
def load_data():
    try:
        engine = create_engine(
            f"mysql+pymysql://{st.secrets['DB_USER']}:{st.secrets['DB_PASS']}@"
            f"{st.secrets['DB_HOST']}:{st.secrets.get('DB_PORT','3306')}/"
            f"{st.secrets['DB_NAME']}",
            pool_pre_ping=True
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
# STATUS PARSER
# =========================================================
def enrich(df):
    def parse(row):
        try:
            resp = json.loads(row["response"]) if isinstance(row["response"], str) else {}
            if resp.get("status") is False:
                return "Failure", str(resp.get("message", "Error"))
            if row["apiName"] == "mobileDetails" and not resp.get("data"):
                return "No Data", "Customer Not Found"
            return "Success", "-"
        except Exception:
            return "Failure", "Parse Error"

    df[["Status", "Failure_Reason"]] = df.apply(parse, axis=1, result_type="expand")
    return df

# =========================================================
# LOAD DATA
# =========================================================
df = load_data()
if df.empty:
    st.warning("Waiting for data…")
    st.stop()

df = enrich(df)

# =========================================================
# SIDEBAR — INTERACTIVE DATE FILTER
# =========================================================
with st.sidebar:
    st.header("🗓️ Date Filter")

    # Presets
    preset = st.selectbox(
        "Quick Range",
        ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "Custom Range"],
        index=1
    )

    max_date = df["createdAt"].max().date()
    min_date = df["createdAt"].min().date()

    # Always render date_input (IMPORTANT)
    date_range = st.date_input(
        "Select Date Range",
        value=(max_date - timedelta(days=7), max_date),
        min_value=min_date,
        max_value=max_date
    )

    # Resolve actual dates
    if preset == "Last 24 Hours":
        start_date = max_date - timedelta(days=1)
        end_date = max_date

    elif preset == "Last 7 Days":
        start_date = max_date - timedelta(days=7)
        end_date = max_date

    elif preset == "Last 30 Days":
        start_date = max_date - timedelta(days=30)
        end_date = max_date

    else:
        # Custom Range
        if isinstance(date_range, tuple) and len(date_range) == 2:
            start_date, end_date = date_range
        else:
            start_date = min_date
            end_date = max_date

    st.caption(f"Showing data from {start_date} → {end_date}")

    df = df[
        (df["createdAt"].dt.date >= start_date) &
        (df["createdAt"].dt.date <= end_date)
    ]


    st.caption(f"Records: {len(df):,}")

# =========================================================
# EXEC SUMMARY
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

# =========================================================
# TABS
# =========================================================
tab_status, tab_alerts, tab_trends, tab_tech, tab_report = st.tabs(
    ["⚡ Live Status", "🚨 Alerts", "📈 Trends", "🔧 Tech", "📄 Report"]
)

# =========================================================
# TAB 1 — STATUS CARDS
# =========================================================
with tab_status:
    summary = df.groupby("apiName")["Status"].value_counts().unstack(fill_value=0)
    summary["Total"] = summary.sum(axis=1)
    summary["Rate"] = (summary.get("Success", 0) / summary["Total"] * 100).round(1)
    summary = summary.sort_values("Rate")

    cols = st.columns(3)
    for i, (api, row) in enumerate(summary.iterrows()):
        icon = "🟢" if row["Rate"] >= 97 else "🟡" if row["Rate"] >= 90 else "🔴"
        with cols[i % 3]:
            st.markdown(f"""
            <div class="api-card">
                <div class="api-header">
                    <span class="api-title">{api}</span>
                    <span>{icon}</span>
                </div>
                <div class="api-metric">{int(row["Total"])}</div>
                <div class="api-sub">Requests</div>
                <div class="api-footer">
                    <span class="success">{int(row.get("Success",0))} Success</span>
                    <span class="failure">{int(row.get("Failure",0))} Failed</span>
                </div>
                <div class="api-footer">
                    <span class="rate">{row["Rate"]}% Success Rate</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

# =========================================================
# TAB 2 — ALERTS
# =========================================================
with tab_alerts:
    sla = df.groupby("apiName")["Status"].apply(lambda x: (x=="Success").mean()*100)
    breaches = sla[sla < 90]

    if breaches.empty:
        st.success("All APIs within SLA 🎉")
    else:
        for api, val in breaches.items():
            st.markdown(
                f"<div class='alert-box'>🚨 <b>{api}</b> – {val:.1f}% success rate</div>",
                unsafe_allow_html=True
            )

# =========================================================
# TAB 3 — TRENDS
# =========================================================
with tab_trends:
    hourly = (
        df.set_index("createdAt")
        .resample("h")["Status"]
        .value_counts()
        .unstack(fill_value=0)
    )
    hourly["Rate"] = hourly.get("Success",0) / hourly.sum(axis=1) * 100

    fig = px.line(hourly, y="Rate", title="Hourly Success Rate (%)")
    fig.add_hline(y=95, line_dash="dot")
    st.plotly_chart(fig, use_container_width=True)

# =========================================================
# TAB 4 — TECH
# =========================================================
with tab_tech:
    failures = df[df["Status"]=="Failure"]
    if failures.empty:
        st.success("No failures detected")
    else:
        st.dataframe(
            failures.groupby(["apiName","Failure_Reason"])
            .size()
            .reset_index(name="Count")
            .sort_values("Count", ascending=False)
            .head(15),
            use_container_width=None
        )

# =========================================================
# TAB 5 — AUTO PDF REPORT
# =========================================================
with tab_report:
    st.subheader("📄 Executive PDF Report")

    def generate_pdf():
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(buffer, pagesize=A4)
        styles = getSampleStyleSheet()
        content = []

        content.append(Paragraph("<b>API Health Executive Report</b>", styles["Title"]))
        content.append(Spacer(1, 12))

        content.append(Paragraph(f"Period: {start_date} to {end_date}", styles["Normal"]))
        content.append(Paragraph(f"System Health: {health}", styles["Normal"]))
        content.append(Paragraph(f"Success Rate: {rate}%", styles["Normal"]))
        content.append(Paragraph(f"Failures: {failure}", styles["Normal"]))
        content.append(Paragraph(f"No Data: {nodata}", styles["Normal"]))

        doc.build(content)
        buffer.seek(0)
        return buffer

    pdf = generate_pdf()

    st.download_button(
        "⬇️ Download Executive PDF",
        data=pdf,
        file_name="API_Executive_Report.pdf",
        mime="application/pdf"
    )
