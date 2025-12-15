import streamlit as st
import pandas as pd
import json
from sqlalchemy import create_engine
import plotly.express as px
from datetime import timedelta
import streamlit.components.v1 as components
from reportlab.platypus import SimpleDocTemplate, Paragraph
from reportlab.lib.styles import getSampleStyleSheet
import io

# =====================================================
# PAGE CONFIG
# =====================================================
st.set_page_config(
    page_title="API Command Center",
    page_icon="⚡",
    layout="wide"
)

# =====================================================
# GLOBAL CSS (KPI CARDS & LAYOUT)
# =====================================================
st.markdown("""
<style>
/* Add breathing room at the top */
.block-container { 
    padding-top: 1rem; 
    padding-bottom: 2rem;
}

/* --- KPI METRIC CARDS --- */
.metric-container {
    display: grid;
    grid-template-columns: repeat(4, 1fr); /* 4 Equal Columns */
    gap: 15px;
    margin-bottom: 30px;
}

.metric-box {
    background: #0f0f0f;
    border: 1px solid #222;
    border-radius: 12px;
    padding: 20px 10px; /* Vertical padding, Horizontal padding */
    text-align: center;
    box-shadow: 0 4px 15px rgba(0,0,0,0.5);
    
    /* Center content vertically and horizontally */
    display: flex;
    flex-direction: column;
    justify-content: center;
    align-items: center;
    min-height: 110px; /* Force consistent height */
    transition: transform 0.2s ease;
}

.metric-box:hover {
    transform: translateY(-3px); /* Subtle hover effect */
    border-color: #444;
}

.metric-label {
    color: #888;
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 1.2px;
    margin-bottom: 8px;
}

.metric-value {
    font-size: 28px; /* Slightly smaller to fit better */
    font-weight: 800;
    color: white;
    line-height: 1.1;
}

/* --- API DETAIL CARDS (Bottom Section) --- */
.api-card {
    background: #0f0f0f;
    border-radius: 14px;
    padding: 20px;
    margin-bottom: 16px;
    min-height: 220px;
    box-shadow: 0 6px 18px rgba(0,0,0,.35);
    position: relative;
    display: flex;
    flex-direction: column;
    justify-content: space-between;
}

/* ... (Keep existing styles for .dot, .success, .failure, etc.) ... */
.dot { width: 10px; height: 10px; border-radius: 50%; position: absolute; top: 20px; right: 20px; }
.green { background: #00c853; } .yellow { background: #f4b400; } .red { background: #ff5252; }
.api-title { color: #aaa; font-size: 13px; font-weight: 600; text-transform: uppercase; margin-bottom: 4px; }
.api-metric { font-size: 38px; font-weight: 700; color: white; line-height: 1; margin-bottom: 2px; }
.api-sub { color: #777; font-size: 12px; margin-bottom: 12px; }
.stats-container { margin-top: auto; }
.api-row { display: flex; justify-content: space-between; font-size: 13px; margin-bottom: 6px; }
.success { color: #00e676; } .failure { color: #ff5252; } .nodata { color: #f4b400; } .rate { color: #64b5f6; }
.tooltip { font-size: 11px; color: #888; background: #1a1a1a; padding: 6px 10px; border-radius: 6px; margin-top: 8px; text-align: center; border: 1px solid #333; }
</style>
""", unsafe_allow_html=True)  

# =====================================================
# LOAD DATA
# =====================================================
@st.cache_data(ttl=120)
def load_data():
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

def enrich(df):
    def parse(row):
        try:
            r = json.loads(row["response"]) if isinstance(row["response"], str) else {}
            if r.get("status") is False:
                return "Failure", str(r.get("message", "Technical Error"))

            if row["apiName"] == "mobileDetails" and not r.get("data"):
                return "No Data", "Customer Not Found"

            if row["apiName"] == "vehicleDetails":
                msg = r.get("data", {}).get("data", {}).get("message")
                if msg == "No Record Found":
                    return "No Data", "Vehicle Not Found"

            return "Success", "-"
        except:
            return "Failure", "Parse Error"

    df[["Status", "Failure_Reason"]] = df.apply(parse, axis=1, result_type="expand")
    return df

df = enrich(load_data())

# =====================================================
# SIDEBAR — DATE FILTER
# =====================================================
with st.sidebar:
    st.header("🗓 Date Filter")

    preset = st.selectbox(
        "Range",
        ["Last 24 Hours", "Last 7 Days", "Last 30 Days", "Custom"],
        index=1
    )

    max_d = df["createdAt"].max().date()
    min_d = df["createdAt"].min().date()

    custom = st.date_input(
        "Custom Range",
        value=(max_d - timedelta(days=7), max_d),
        min_value=min_d,
        max_value=max_d
    )

    if preset == "Last 24 Hours":
        start, end = max_d - timedelta(days=1), max_d
    elif preset == "Last 7 Days":
        start, end = max_d - timedelta(days=7), max_d
    elif preset == "Last 30 Days":
        start, end = max_d - timedelta(days=30), max_d
    else:
        start, end = custom

    df = df[
        (df["createdAt"].dt.date >= start) &
        (df["createdAt"].dt.date <= end)
    ]

# =====================================================
# EXEC SUMMARY (FIXED: PROPER KPI CARDS)
# =====================================================
total = len(df)
success = (df["Status"] == "Success").sum()
failure = (df["Status"] == "Failure").sum()
nodata = (df["Status"] == "No Data").sum()
rate = round(success / total * 100, 1) if total else 0

# Determine Health Color
health = "CRITICAL" if rate < 90 else "DEGRADED" if rate < 97 else "HEALTHY"
health_color = "#ff5252" if health == "CRITICAL" else "#f4b400" if health == "DEGRADED" else "#00e676"

# RENDER HTML (Must be flush left to avoid code blocks)
st.markdown(f"""
<div class="metric-container">
<div class="metric-box">
<div class="metric-label">System Health</div>
<div class="metric-value" style="color: {health_color}; text-shadow: 0 0 10px {health_color}44;">{health}</div>
</div>
<div class="metric-box">
<div class="metric-label">Success Rate</div>
<div class="metric-value">{rate}%</div>
</div>
<div class="metric-box">
<div class="metric-label">Total Failures</div>
<div class="metric-value" style="color: #ff5252">{failure}</div>
</div>
<div class="metric-box">
<div class="metric-label">No Data Events</div>
<div class="metric-value" style="color: #f4b400">{nodata}</div>
</div>
</div>
""", unsafe_allow_html=True)

st.divider()


# =====================================================
# TABS
# =====================================================
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "⚡ Live Status",
    "🚨 Alerts",
    "📈 Trends",
    "🔧 Tech",
    "📊 Business Impact",
    "📄 Report"
])

def api_card(api, row):
    dot = "green" if row["Success_Rate"] >= 97 else "yellow" if row["Success_Rate"] >= 90 else "red"
    loss = int(row["No Data"] * 0.6)

    # IMPORTANT: The HTML below must be flush-left (no spaces at start of lines)
    # otherwise Streamlit treats it as a code block.
    html = f"""
<div class="api-card">
<div class="dot {dot}"></div>
<div>
<div class="api-title">{api.upper()}</div>
<div class="api-metric">{int(row["Total"])}</div>
<div class="api-sub">Total Requests</div>
</div>
<div class="stats-container">
<div class="api-row">
<span class="success">✔ {int(row["Success"])}</span>
<span class="failure">✖ {int(row["Failure"])}</span>
</div>
<div class="api-row">
<span class="nodata">⚠ {int(row["No Data"])} Empty</span>
<span class="rate">⚡ {row["Success_Rate"]}%</span>
</div>
<div class="tooltip">
Impact: ~{loss} potential leads lost
</div>
</div>
</div>
"""
    st.markdown(html, unsafe_allow_html=True)

# =====================================================
# LIVE STATUS
# =====================================================
with tab1:
    s = df.groupby("apiName")["Status"].value_counts().unstack(fill_value=0)
    for c in ["Success", "Failure", "No Data"]:
        if c not in s.columns:
            s[c] = 0

    s["Total"] = s.sum(axis=1)
    s["Success_Rate"] = (s["Success"] / s["Total"] * 100).round(1)

    cols = st.columns(3)
    for i, (api, row) in enumerate(s.iterrows()):
        with cols[i % 3]:
            api_card(api, row)

# =====================================================
# ALERTS
# =====================================================
with tab2:
    breaches = s[s["Success_Rate"] < 90]
    if breaches.empty:
        st.success("All APIs within SLA")
    else:
        st.dataframe(breaches[["Success_Rate"]])

# =====================================================
# TRENDS
# =====================================================
with tab3:
    h = df.set_index("createdAt").resample("h")["Status"].value_counts().unstack(fill_value=0)
    h["Rate"] = h.get("Success", 0) / h.sum(axis=1) * 100
    fig = px.line(h, y="Rate", title="Hourly Success Rate (%)")
    fig.add_hline(y=95, line_dash="dot")
    st.plotly_chart(fig, use_container_width=True)

# =====================================================
# TECH — ERROR GROUPING (RESTORED)
# =====================================================
with tab4:
    f = df[df["Status"] == "Failure"]
    st.dataframe(
        f.groupby(["apiName", "Failure_Reason"])
         .size()
         .reset_index(name="Count")
         .sort_values("Count", ascending=False),
        use_container_width=True
    )

# =====================================================
# BUSINESS IMPACT — CLEAN FUNNEL + INCIDENTS
# =====================================================
with tab5:
    FUNNEL = [
        ("mobileDetails", "Mobile Prefill"),
        ("panDetails", "PAN"),
        ("cibilDetails", "CIBIL"),
        ("vehicleDetails", "Vehicle"),
        ("idfcCreateLoanApplicationId", "Loan Creation")
    ]

    rows = []
    base = None
    for api, label in FUNNEL:
        d = df[df["apiName"] == api]
        t = len(d)
        s_cnt = (d["Status"] == "Success").sum()
        if base is None:
            base = t
        drop = round((t - s_cnt) / base * 100, 1) if base else 0
        rows.append({
            "Stage": label,
            "Requests": t,
            "Success": s_cnt,
            "No Data": (d["Status"] == "No Data").sum(),
            "Failure": (d["Status"] == "Failure").sum(),
            "Drop %": drop
        })

    st.subheader("Conversion Funnel")
    st.dataframe(pd.DataFrame(rows), use_container_width=True)

    st.subheader("Incident Groups")
    st.dataframe(
        df[df["Status"] != "Success"]
        .groupby(["apiName", "Failure_Reason"])
        .size()
        .reset_index(name="Count")
        .sort_values("Count", ascending=False),
        use_container_width=True
    )

# =====================================================
# REPORT
# =====================================================
with tab6:
    def pdf():
        buf = io.BytesIO()
        doc = SimpleDocTemplate(buf)
        styles = getSampleStyleSheet()
        doc.build([
            Paragraph("API Executive Report", styles["Title"]),
            Paragraph(f"Success Rate: {rate}%", styles["Normal"]),
            Paragraph(f"Failures: {failure}", styles["Normal"]),
            Paragraph(f"No Data: {nodata}", styles["Normal"])
        ])
        buf.seek(0)
        return buf

    st.download_button("⬇ Download PDF", pdf(), "API_Report.pdf", "application/pdf")
