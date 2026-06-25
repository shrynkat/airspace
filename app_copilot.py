import streamlit as st
import os
import json
import base64
from google.oauth2 import service_account
from google.cloud import bigquery

# ─────────────────────────────────────────
# PAGE CONFIG
# ─────────────────────────────────────────

st.set_page_config(
    page_title="Airspace Disruption Copilot",
    page_icon="🤖",
    layout="wide"
)

# ─────────────────────────────────────────
# CREDENTIALS SETUP
# ─────────────────────────────────────────

def setup_credentials():
    if os.path.exists("credentials.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"
    else:
        creds_bytes = base64.b64decode(st.secrets["CREDENTIALS_B64"])
        creds_info = json.loads(creds_bytes)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        import tempfile
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(creds_info, f)
            os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = f.name

    if "GROQ_API_KEY" not in os.environ:
        try:
            os.environ["GROQ_API_KEY"] = st.secrets["GROQ_API_KEY"]
        except:
            pass

setup_credentials()

# Import agent after credentials are set
from agent import run_agent

# ─────────────────────────────────────────
# HEADER
# ─────────────────────────────────────────

st.title("🤖 Airspace Disruption Copilot")
st.caption("Powered by LangGraph multi-agent reasoning — BigQuery + Live Weather + DOT Compliance")

with st.expander("How to use this copilot"):
    st.markdown("""
    **Ask questions like:**
    - *"My flight on tail N691CA is delayed 3 hours at Chicago O'Hare. The gate agent says weather. What are my options?"*
    - *"What is the delay history of aircraft N145AA?"*
    - *"My flight AA125 on tail N200PQ has been delayed 4 hours at Atlanta. Am I eligible for a refund?"*
    
    **What the copilot does:**
    1. Queries your BigQuery warehouse for the aircraft's real delay history
    2. Pulls live METAR weather data for the airport right now
    3. Evaluates your DOT cash refund eligibility
    4. Synthesizes all three into a clear, actionable response
    """)

st.divider()

# ─────────────────────────────────────────
# CHAT HISTORY
# ─────────────────────────────────────────

if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

# Display existing chat history
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# ─────────────────────────────────────────
# CHAT INPUT
# ─────────────────────────────────────────

user_input = st.chat_input("Describe your flight situation...")

if user_input:
    # Display user message
    with st.chat_message("user"):
        st.markdown(user_input)

    st.session_state.chat_history.append({
        "role": "user",
        "content": user_input
    })

    # Run agent with live status display
    with st.chat_message("assistant"):
        with st.status("Agent reasoning in progress...", expanded=True) as status:

            st.write("🔍 **Data Analyst Node** — Querying BigQuery flight history...")
            
            # We need to capture intermediate results
            # Run the full agent
            result = run_agent(user_input)

            flight_data = result.get("flight_data", {})
            weather_data = result.get("weather_data", {})
            compliance_data = result.get("compliance_data", {})

            # Show flight data results
            if flight_data.get("status") == "success":
                st.write(f"   ✅ Found **{flight_data.get('total_records_returned')}** flight records")
                summary = flight_data.get("summary", {})
                st.write(f"   📊 Avg arrival delay: **{summary.get('avg_arrival_delay_minutes')} min**")
                st.write(f"   🔗 Most common cause: **{summary.get('most_common_delay_cause')}**")
            else:
                st.write(f"   ⚠️ Flight data: {flight_data.get('message', 'unavailable')}")

            st.write("🌤️ **Weather Expert Node** — Checking live METAR data...")

            # Show weather results
            if weather_data.get("status") == "success":
                st.write(f"   ✅ Airport: **{weather_data.get('airport')}**")
                st.write(f"   🌡️ Raw METAR: `{weather_data.get('raw_metar', 'N/A')}`")
                st.write(f"   💨 Wind: **{weather_data.get('wind_speed_kt')} knots**")
                st.write(f"   👁️ Visibility: **{weather_data.get('visibility_miles')} miles**")
            else:
                st.write(f"   ⚠️ Weather data: {weather_data.get('message', 'unavailable')}")

            st.write("⚖️ **Compliance Node** — Evaluating DOT 3-hour rule...")

            # Show compliance results
            if compliance_data.get("status") == "success":
                legal_status = compliance_data.get("legal_status")
                delay_minutes = compliance_data.get("delay_minutes")
                
                if legal_status == "ELIGIBLE":
                    st.write(f"   ✅ Delay: **{delay_minutes} min** — **ELIGIBLE for cash refund**")
                elif legal_status == "REVIEW_REQUIRED":
                    st.write(f"   ⚠️ Delay: **{delay_minutes} min** — **REVIEW REQUIRED**")
                else:
                    st.write(f"   ℹ️ Delay: **{delay_minutes} min** — **NOT eligible** (below threshold)")

            st.write("📋 **Synthesizer Node** — Generating final response...")
            st.write(f"   ✅ Complete — used **{result.get('loop_count')} / 5** agent loops")

            status.update(label="Analysis complete", state="complete", expanded=False)

        # Display final response
        final_response = result.get("final_response", "No response generated.")
        st.markdown(final_response)

        # Show raw data in expanders
        col1, col2, col3 = st.columns(3)

        with col1:
            with st.expander("Flight data payload"):
                st.json(flight_data)

        with col2:
            with st.expander("Weather data payload"):
                st.json(weather_data)

        with col3:
            with st.expander("Compliance data payload"):
                st.json(compliance_data)

    # Save assistant response to history
    st.session_state.chat_history.append({
        "role": "assistant",
        "content": result.get("final_response", "")
    })