import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from google.cloud import bigquery
import os
import json
import tempfile

# Credentials — works both locally and on Streamlit Cloud
PROJECT_ID = "airspace-platform"

from google.oauth2 import service_account

def get_bigquery_client():
    if os.path.exists("credentials.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"
        return bigquery.Client(project=PROJECT_ID)
    else:
        import base64
        from google.oauth2 import service_account
        creds_bytes = base64.b64decode(st.secrets["CREDENTIALS_B64"])
        creds_info = json.loads(creds_bytes)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(project=PROJECT_ID, credentials=credentials)

client = get_bigquery_client()

# Page setup
st.set_page_config(
    page_title="Airspace Operations Dashboard",
    page_icon="✈️",
    layout="wide"
)

st.title("✈️ National Airspace Bottleneck Platform")
st.caption("Operational intelligence for U.S. aviation delay analysis — January 2024")

# ─────────────────────────────────────────
# DATA LOADERS
# ─────────────────────────────────────────

@st.cache_data(ttl=600)
def load_delay_summary():
    query = """
        select
            delay_root_cause,
            count(*) as flight_count,
            round(avg(arr_delay), 2) as avg_arr_delay,
            round(avg(dep_delay), 2) as avg_dep_delay,
            round(avg(inherited_delay_minutes), 2) as avg_inherited_delay
        from `airspace-platform.airspace_raw.tail_delay_lineage`
        where arr_delay is not null
        group by delay_root_cause
        order by flight_count desc
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=600)
def load_airport_congestion():
    query = """
        select
            dest_airport_id,
            count(*) as total_flights,
            round(avg(arr_delay), 2) as avg_arr_delay,
            countif(arr_delay > 15) as delayed_flights,
            round(countif(arr_delay > 15) / count(*) * 100, 2) as delay_rate_pct
        from `airspace-platform.airspace_raw.tail_delay_lineage`
        where arr_delay is not null
        group by dest_airport_id
        having count(*) > 100
        order by avg_arr_delay desc
        limit 30
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=600)
def load_buffer_erosion():
    query = """
        select
            op_unique_carrier,
            count(*) as total_flights,
            countif(dep_delay > 0) as delayed_departures,
            round(avg(inherited_delay_minutes), 2) as avg_inherited_delay,
            countif(inherited_delay_minutes > 15) as buffer_breached_count,
            round(countif(inherited_delay_minutes > 15) / count(*) * 100, 2) as buffer_breach_rate_pct
        from `airspace-platform.airspace_raw.tail_delay_lineage`
        group by op_unique_carrier
        having count(*) > 200
        order by buffer_breach_rate_pct desc
    """
    return client.query(query).to_dataframe()

@st.cache_data(ttl=600)
def load_tail_lineage(tail_number):
    query = f"""
        select
            fl_date,
            op_unique_carrier,
            tail_num,
            origin_airport_id,
            dest_airport_id,
            dep_delay,
            arr_delay,
            inherited_delay_minutes,
            delay_root_cause,
            prev_flight_arr_delay,
            prev_flight_origin_airport_id
        from `airspace-platform.airspace_raw.tail_delay_lineage`
        where tail_num = '{tail_number}'
        order by fl_date asc
    """
    return client.query(query).to_dataframe()

# ─────────────────────────────────────────
# SECTION 1: KPI METRICS
# ─────────────────────────────────────────

st.subheader("Network overview")

delay_summary = load_delay_summary()
airport_data = load_airport_congestion()
buffer_data = load_buffer_erosion()

total_flights = delay_summary["flight_count"].sum()
carrier_controlled = delay_summary[
    delay_summary["delay_root_cause"] == "carrier_controlled"
]["flight_count"].sum()
faa_controlled = delay_summary[
    delay_summary["delay_root_cause"] == "faa_controlled"
]["flight_count"].sum()
avg_inherited = delay_summary["avg_inherited_delay"].mean()

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total flights analyzed", f"{total_flights:,}")
col2.metric("Carrier-controlled delays", f"{carrier_controlled:,}")
col3.metric("FAA-controlled delays", f"{faa_controlled:,}")
col4.metric("Avg inherited delay (min)", f"{avg_inherited:.1f}")

st.divider()

# ─────────────────────────────────────────
# SECTION 2: DELAY ROOT CAUSE BREAKDOWN
# ─────────────────────────────────────────

st.subheader("Delay root cause breakdown")

col1, col2 = st.columns(2)

with col1:
    fig_pie = px.pie(
        delay_summary,
        names="delay_root_cause",
        values="flight_count",
        title="Flights by root cause",
        color_discrete_sequence=px.colors.qualitative.Set2
    )
    fig_pie.update_traces(textposition="inside", textinfo="percent+label")
    st.plotly_chart(fig_pie, use_container_width=True)

with col2:
    fig_bar = px.bar(
        delay_summary,
        x="delay_root_cause",
        y="avg_arr_delay",
        title="Average arrival delay by root cause (minutes)",
        color="delay_root_cause",
        color_discrete_sequence=px.colors.qualitative.Set2,
        labels={"delay_root_cause": "Root cause", "avg_arr_delay": "Avg arrival delay (min)"}
    )
    fig_bar.update_layout(showlegend=False)
    st.plotly_chart(fig_bar, use_container_width=True)

st.divider()

# ─────────────────────────────────────────
# SECTION 3: AIRPORT CONGESTION INDEX
# ─────────────────────────────────────────

st.subheader("Airport congestion index")
st.caption("Top 30 airports by average arrival delay — airports with over 100 flights in January 2024")

fig_airport = px.bar(
    airport_data,
    x="dest_airport_id",
    y="avg_arr_delay",
    color="delay_rate_pct",
    color_continuous_scale="Reds",
    title="Average arrival delay per airport (minutes)",
    labels={
        "dest_airport_id": "Airport ID",
        "avg_arr_delay": "Avg arrival delay (min)",
        "delay_rate_pct": "Delay rate (%)"
    }
)
fig_airport.update_layout(xaxis_tickangle=45)
st.plotly_chart(fig_airport, use_container_width=True)

st.divider()

# ─────────────────────────────────────────
# SECTION 4: BUFFER EROSION INDEX
# ─────────────────────────────────────────

st.subheader("Buffer erosion index")
st.caption("Carriers where inherited delays are breaching the 15-minute turnaround threshold most often")

fig_buffer = px.bar(
    buffer_data,
    x="op_unique_carrier",
    y="buffer_breach_rate_pct",
    color="avg_inherited_delay",
    color_continuous_scale="Oranges",
    title="Buffer breach rate by carrier (%)",
    labels={
        "op_unique_carrier": "Carrier",
        "buffer_breach_rate_pct": "Buffer breach rate (%)",
        "avg_inherited_delay": "Avg inherited delay (min)"
    }
)
st.plotly_chart(fig_buffer, use_container_width=True)

st.divider()

# ─────────────────────────────────────────
# SECTION 5: TAIL NUMBER LINEAGE TRACKER
# ─────────────────────────────────────────

st.subheader("Tail-number lineage tracker")
st.caption("Enter an aircraft tail number to trace its full delay chain across January 2024")

tail_input = st.text_input("Tail number", placeholder="e.g. N691CA")

if tail_input:
    tail_data = load_tail_lineage(tail_input.strip().upper())

    if tail_data.empty:
        st.warning(f"No flights found for tail number {tail_input.upper()}. Check the number and try again.")
    else:
        st.success(f"Found {len(tail_data)} flights for {tail_input.upper()}")

        col1, col2, col3 = st.columns(3)
        col1.metric("Total flights", len(tail_data))
        col2.metric("Avg arrival delay (min)", f"{tail_data['arr_delay'].mean():.1f}")
        col3.metric("Avg inherited delay (min)", f"{tail_data['inherited_delay_minutes'].mean():.1f}")

        fig_tail = px.line(
            tail_data,
            x="fl_date",
            y=["arr_delay", "inherited_delay_minutes"],
            title=f"Delay chain for {tail_input.upper()}",
            labels={"fl_date": "Date", "value": "Minutes", "variable": "Metric"},
            markers=True
        )
        st.plotly_chart(fig_tail, use_container_width=True)

        st.dataframe(
            tail_data[[
                "fl_date", "op_unique_carrier", "origin_airport_id",
                "dest_airport_id", "dep_delay", "arr_delay",
                "inherited_delay_minutes", "delay_root_cause"
            ]],
            use_container_width=True
        )