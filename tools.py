import os
import requests
from pydantic import BaseModel, Field
from google.cloud import bigquery
from typing import Optional

# ─────────────────────────────────────────
# BIGQUERY CLIENT SETUP
# ─────────────────────────────────────────

def get_bigquery_client():
    if os.path.exists("credentials.json"):
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"
        return bigquery.Client(project="airspace-platform")
    else:
        import json
        import base64
        import tempfile
        from google.oauth2 import service_account
        import streamlit as st
        creds_bytes = base64.b64decode(st.secrets["CREDENTIALS_B64"])
        creds_info = json.loads(creds_bytes)
        credentials = service_account.Credentials.from_service_account_info(
            creds_info,
            scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        return bigquery.Client(project="airspace-platform", credentials=credentials)

# ─────────────────────────────────────────
# PYDANTIC INPUT SCHEMAS
# ─────────────────────────────────────────

class FlightHistoryInput(BaseModel):
    """Input schema for querying flight delay history by tail number."""
    tail_number: str = Field(
        ...,
        description="Aircraft tail number to query. Must be uppercase, e.g. N691CA"
    )
    limit: Optional[int] = Field(
        default=10,
        description="Maximum number of flight records to return. Default is 10."
    )

class WeatherInput(BaseModel):
    """Input schema for querying live METAR weather data for an airport."""
    airport_icao: str = Field(
        ...,
        description="ICAO airport code to get weather for. e.g. KORD for Chicago O'Hare, KATL for Atlanta"
    )

# ─────────────────────────────────────────
# TOOL 1: BIGQUERY FLIGHT HISTORY
# ─────────────────────────────────────────

def query_flight_history(tail_number: str, limit: int = 10) -> dict:
    """
    Query BigQuery for the delay history of a specific aircraft tail number.
    Returns flight records with delay causes and inherited delay minutes.
    """
    # Validate input with Pydantic
    validated = FlightHistoryInput(tail_number=tail_number.upper(), limit=limit)

    client = get_bigquery_client()

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
        where tail_num = '{validated.tail_number}'
        order by fl_date desc
        limit {validated.limit}
    """

    try:
        df = client.query(query).to_dataframe()

        if df.empty:
            return {{
                "status": "not_found",
                "message": f"No flight records found for tail number {validated.tail_number}",
                "tail_number": validated.tail_number,
                "records": []
            }}

        records = df.to_dict(orient="records")

        # Convert timestamps to strings for JSON serialization
        for record in records:
            for key, value in record.items():
                if hasattr(value, 'isoformat'):
                    record[key] = str(value)
                elif value != value:  # NaN check
                    record[key] = None

        # Compute summary stats
        avg_arr_delay = df['arr_delay'].mean()
        avg_inherited = df['inherited_delay_minutes'].mean()
        most_common_cause = df['delay_root_cause'].mode()[0] if not df['delay_root_cause'].empty else "unknown"

        return {
            "status": "success",
            "tail_number": validated.tail_number,
            "total_records_returned": len(records),
            "summary": {
                "avg_arrival_delay_minutes": round(float(avg_arr_delay), 2) if avg_arr_delay == avg_arr_delay else None,
                "avg_inherited_delay_minutes": round(float(avg_inherited), 2) if avg_inherited == avg_inherited else None,
                "most_common_delay_cause": most_common_cause
            },
            "records": records
        }

    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "tail_number": validated.tail_number,
            "records": []
        }

# ─────────────────────────────────────────
# TOOL 2: LIVE WEATHER (METAR)
# ─────────────────────────────────────────

def query_airport_weather(airport_icao: str) -> dict:
    """
    Query live METAR weather data from aviationweather.gov for a specific airport.
    Returns current sky conditions, wind, visibility, and flight rules category.
    """
    # Validate input with Pydantic
    validated = WeatherInput(airport_icao=airport_icao.upper())

    url = f"https://aviationweather.gov/api/data/metar?ids={validated.airport_icao}&format=json"

    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()

        if not data:
            return {
                "status": "not_found",
                "message": f"No METAR data found for airport {validated.airport_icao}",
                "airport": validated.airport_icao
            }

        metar = data[0]

        return {
            "status": "success",
            "airport": validated.airport_icao,
            "observation_time": metar.get("obsTime", "unknown"),
            "raw_metar": metar.get("rawOb", "unavailable"),
            "temperature_c": metar.get("temp", None),
            "wind_speed_kt": metar.get("wspd", None),
            "wind_direction": metar.get("wdir", None),
            "visibility_miles": metar.get("visib", None),
            "sky_condition": metar.get("skyCondition", None),
            "flight_rules": metar.get("fltcat", None),
            "weather_string": metar.get("wxString", None),
            "cloud_coverage": metar.get("clouds", None)
        }

    except requests.exceptions.Timeout:
        return {
            "status": "error",
            "message": "Weather API request timed out after 10 seconds",
            "airport": validated.airport_icao
        }
    except Exception as e:
        return {
            "status": "error",
            "message": str(e),
            "airport": validated.airport_icao
        }

# ─────────────────────────────────────────
# DOT COMPLIANCE CHECKER
# ─────────────────────────────────────────

def check_dot_compliance(delay_minutes: float, delay_cause: str) -> dict:
    """
    Check whether a flight delay qualifies for a DOT cash refund.
    Returns legal status and recommended action.
    """
    DOT_THRESHOLD_MINUTES = 180  # 3 hours

    qualifies = delay_minutes >= DOT_THRESHOLD_MINUTES
    carrier_controlled = delay_cause in [
        "carrier_controlled",
        "carrier_cancellation",
        "mixed_carrier_weather"
    ]

    if qualifies and carrier_controlled:
        legal_status = "ELIGIBLE"
        recommendation = (
            f"Your delay of {delay_minutes} minutes is carrier-controlled and exceeds "
            f"the DOT 3-hour threshold. You are legally entitled to a full cash refund "
            f"to your original form of payment if you choose not to rebook."
        )
    elif qualifies and not carrier_controlled:
        legal_status = "REVIEW_REQUIRED"
        recommendation = (
            f"Your delay of {delay_minutes} minutes exceeds the DOT 3-hour threshold "
            f"but is classified as {delay_cause}. Weather and FAA delays may still "
            f"qualify depending on carrier policy. Request written documentation of "
            f"the delay cause from the carrier."
        )
    else:
        legal_status = "NOT_ELIGIBLE"
        recommendation = (
            f"Your delay of {delay_minutes} minutes has not yet crossed the DOT "
            f"3-hour threshold. Monitor the delay and reassess if it reaches 180 minutes."
        )

    return {
        "status": "success",
        "delay_minutes": delay_minutes,
        "delay_cause": delay_cause,
        "dot_threshold_minutes": DOT_THRESHOLD_MINUTES,
        "qualifies_for_refund": qualifies,
        "carrier_controlled": carrier_controlled,
        "legal_status": legal_status,
        "recommendation": recommendation
    }