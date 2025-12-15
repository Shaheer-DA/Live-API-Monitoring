import streamlit as st
import pandas as pd
import json
from sqlalchemy import create_engine
import plotly.express as px
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta

load_dotenv()

# --- PAGE CONFIGURATION ---
st.set_page_config(page_title="API Command Center", page_icon="⚡", layout="wide")

# --- CUSTOM CSS ---
st.markdown("""
<style>
    .api-card {
        background-color: #1E1E1E;
        border-radius: 10px;
        padding: 20px;
        margin-bottom: 20px;
        border: 1px solid #333;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
    }
    .card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        color: #888;
        font-size: 14px;
        font-weight: 600;
        text-transform: uppercase;
        margin-bottom: 15px;
    }
    .card-metric {
        font-size: 36px;
        font-weight: 700;
        color: #FFF;
        margin-bottom: 5px;
    }
    .metric-label {
        color: #666;
        font-size: 14px;
        margin-bottom: 15px;
    }
    .divider {
        height: 1px;
        background-color: #333;
        margin: 15px 0;
    }
    .card-footer {
        display: flex;
        justify-content: space-between;
        font-size: 13px;
        font-weight: 600;
    }
    .success-text { color: #00CC96; }
    .fail-text { color: #EF553B; }
    .nodata-text { color: #FFA15A; }
</style>
""", unsafe_allow_html=True)

# --- IMPROVED DATABASE CONNECTION ---
@st.cache_data(ttl=5) 
def load_data():
    # 1. Try fetching from Streamlit Secrets (Cloud)
    #    (This works even if you didn't add the [env] header!)
    try:
        db_host = st.secrets["DB_HOST"]
        db_user = st.secrets["DB_USER"]
        db_pass = st.secrets["DB_PASS"]
        db_name = st.secrets["DB_NAME"]
    except:
        # 2. If that fails, try local .env file (Localhost)
        db_host = os.getenv("DB_HOST")
        db_user = os.getenv("DB_USER")
        db_pass = os.getenv("DB_PASS")
        db_name = os.getenv("DB_NAME")

    # Safety Check
    if not db_host:
        st.error("❌ Database config not found! Please check Secrets or .env file.")
        return pd.DataFrame()

    # Create Connection
    connection_string = f"mysql+pymysql://{db_user}:{db_pass}@{db_host}/{db_name}"
    engine = create_engine(connection_string)
    
    query = "SELECT * FROM cpl_api_logs ORDER BY createdAt DESC"
    
    try:
        with engine.connect() as conn:
            df = pd.read_sql(query, conn)
        
        if not df.empty:
            df['createdAt'] = pd.to_datetime(df['createdAt'])
        return df
        
    except Exception as e:
        st.error(f"🚨 Connection Failed: {e}")  
        return pd.DataFrame()
# --- 2. PROCESSING LOGIC ---
def process_data(df):
    # We apply the logic to create a new 'Status' column for easier filtering
    def get_status(row):
        try:
            # Handle JSON parsing safely
            resp_str = row['response']
            resp = json.loads(resp_str) if isinstance(resp_str, str) else resp_str
            
            # 1. Technical Failure
            if resp.get('status') is False:
                return 'Failure'

            # 2. API Specific Business Logic
            api = row['apiName']
            
            if api == 'mobileDetails':
                if resp.get('data') is None:
                    return 'No Data'
            
            elif api == 'vehicleDetails':
                try:
                    if resp.get('data', {}).get('data', {}).get('message') == 'No Record Found':
                        return 'No Data'
                except:
                    pass
            
            return 'Success'
        except:
            return 'Failure'

    df['Status'] = df.apply(get_status, axis=1)
    return df

# --- 3. UI COMPONENTS ---
def render_kpi_card(metrics):
    icon_map = {
        'panDetails': '💳', 'mobileDetails': '📱', 
        'cibilDetails': '📈', 'vehicleDetails': '🚛', 'ibbDetails': '🏛️'
    }
    icon = icon_map.get(metrics['name'], '⚡')
    
    html = f"""
    <div class="api-card">
        <div class="card-header">
            <span>{metrics['name']}</span>
            <span>{icon}</span>
        </div>
        <div class="card-metric">{metrics['total']}</div>
        <div class="metric-label">reqs</div>
        <div class="divider"></div>
        <div class="card-footer">
            <span class="success-text">{metrics['success']} SUCCESS</span>
            <span class="fail-text">{metrics['failed']} FAILED</span>
        </div>
        <div class="card-footer" style="margin-top:5px;">
            <span class="nodata-text">{metrics['no_data']} NO DATA</span>
            <span style="color:#888">{metrics['rate']}% RATE</span>
        </div>
    </div>
    """
    st.markdown(html, unsafe_allow_html=True)

# --- MAIN APP ---
st.title("⚡ API Command Center")

try:
    df_raw = load_data()
    df = process_data(df_raw)

    # --- SIDEBAR: DATE FILTER ---
    st.sidebar.header("📅 Date Filter")
    
    # Get min/max dates from data for defaults
    min_date = df['createdAt'].min().date()
    max_date = df['createdAt'].max().date()
    
    # Date Picker Widget
    date_range = st.sidebar.date_input(
        "Select Date Range",
        value=(min_date, max_date),
        min_value=min_date,
        max_value=max_date
    )

    # Filter Logic
    if len(date_range) == 2:
        start_date, end_date = date_range
        # Filter dataframe mask
        mask = (df['createdAt'].dt.date >= start_date) & (df['createdAt'].dt.date <= end_date)
        df_filtered = df.loc[mask]
    else:
        df_filtered = df # Fallback if single date selected

    # --- SIDEBAR: API FILTER ---
    st.sidebar.header("🔍 API Filter")
    all_apis = df_filtered['apiName'].unique()
    selected_apis = st.sidebar.multiselect("Select APIs", all_apis, default=all_apis)
    
    if selected_apis:
        df_filtered = df_filtered[df_filtered['apiName'].isin(selected_apis)]

    st.markdown(f"**Showing data from {len(df_filtered)} records**")

    # --- SECTION 1: KPI CARDS ---
    st.subheader("Live Status")
    
    # Calculate metrics for each API
    api_metrics = []
    for api in selected_apis:
        sub = df_filtered[df_filtered['apiName'] == api]
        total = len(sub)
        success = len(sub[sub['Status'] == 'Success'])
        failed = len(sub[sub['Status'] == 'Failure'])
        no_data = len(sub[sub['Status'] == 'No Data'])
        
        rate = round((success / total * 100), 1) if total > 0 else 0
        
        api_metrics.append({
            "name": api, "total": total, "success": success, 
            "failed": failed, "no_data": no_data, "rate": rate
        })

    # Render Cards (3 columns)
    cols = st.columns(3)
    for i, metric in enumerate(api_metrics):
        with cols[i % 3]:
            render_kpi_card(metric)

    st.markdown("---")

    # --- SECTION 2: SUMMARY TABLE (The "Matching" Table) ---
    st.subheader("📊 Detailed Summary Table")
    
    # Pivot logic to create the exact table you wanted
    summary_table = df_filtered.groupby('apiName')['Status'].value_counts().unstack(fill_value=0)
    
    # Ensure all columns exist even if count is 0
    for col in ['Success', 'Failure', 'No Data']:
        if col not in summary_table.columns:
            summary_table[col] = 0
            
    # Calculate Totals and Rates
    summary_table['Total Hits'] = summary_table['Success'] + summary_table['Failure'] + summary_table['No Data']
    summary_table['Success %'] = round((summary_table['Success'] / summary_table['Total Hits']) * 100, 2)
    
    # Reorder columns to match your screenshot
    summary_table = summary_table[['Total Hits', 'Success', 'Failure', 'No Data', 'Success %']]
    
    # Display the table
    st.dataframe(summary_table, use_container_width=None)

except Exception as e:
    st.error(f"Waiting for data or connection error: {e}")