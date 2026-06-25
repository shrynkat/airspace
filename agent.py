import os
from typing import TypedDict, Literal, Annotated
from langgraph.graph import StateGraph, END
from langchain_groq import ChatGroq
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
import operator

from tools import query_flight_history, query_airport_weather, check_dot_compliance

# ─────────────────────────────────────────
# GROQ LLM SETUP
# ─────────────────────────────────────────

def get_llm():
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        try:
            import streamlit as st
            api_key = st.secrets["GROQ_API_KEY"]
        except:
            raise ValueError("GROQ_API_KEY not found in environment or Streamlit secrets")
    
    return ChatGroq(
        model="llama-3.3-70b-versatile",
        api_key=api_key,
        temperature=0
    )

# ─────────────────────────────────────────
# STATE DEFINITION
# ─────────────────────────────────────────

class AgentState(TypedDict):
    # The original user query
    user_query: str
    # All messages in the conversation
    messages: Annotated[list, operator.add]
    # Data collected by each agent
    flight_data: dict
    weather_data: dict
    compliance_data: dict
    # Which agent runs next
    next_agent: str
    # Circuit breaker — max 5 loops
    loop_count: int
    # Final response to show user
    final_response: str

# ─────────────────────────────────────────
# AGENT NODE 1: DATA ANALYST
# ─────────────────────────────────────────

def data_analyst_node(state: AgentState) -> AgentState:
    print("🔍 Data Analyst Node: Querying BigQuery...")
    
    llm = get_llm()
    
    # Extract tail number from user query
    system_prompt = """You are a flight data analyst. Your only job is to extract 
    the aircraft tail number from the user's query. 
    Respond with ONLY the tail number in uppercase (e.g. N691CA).
    If no tail number is found, respond with UNKNOWN."""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["user_query"])
    ]
    
    response = llm.invoke(messages)
    tail_number = response.content.strip().upper()
    
    if tail_number == "UNKNOWN" or not tail_number:
        flight_data = {
            "status": "not_found",
            "message": "No tail number found in the query",
            "records": []
        }
    else:
        flight_data = query_flight_history(tail_number, limit=5)
    
    print(f"   Tail number: {tail_number}")
    print(f"   Status: {flight_data['status']}")
    
    return {
        **state,
        "flight_data": flight_data,
        "messages": [AIMessage(content=f"Data Analyst: Queried flight history for {tail_number}. Status: {flight_data['status']}")],
        "next_agent": "weather_expert",
        "loop_count": state["loop_count"] + 1
    }

# ─────────────────────────────────────────
# AGENT NODE 2: WEATHER EXPERT
# ─────────────────────────────────────────

def weather_expert_node(state: AgentState) -> AgentState:
    print("🌤️  Weather Expert Node: Checking live METAR...")
    
    llm = get_llm()
    
    # Extract airport code from user query
    system_prompt = """You are an aviation weather expert. Your only job is to extract 
    the ICAO airport code from the user's query.
    Convert common airport names to ICAO codes:
    - Chicago O'Hare = KORD
    - Atlanta = KATL
    - Dallas Fort Worth = KDFW
    - Los Angeles = KLAX
    - New York JFK = KJFK
    - New York LaGuardia = KLGA
    - Denver = KDEN
    - Seattle = KSEA
    - Miami = KMIA
    - Boston = KBOS
    Respond with ONLY the ICAO code in uppercase (e.g. KORD).
    If no airport is found, respond with UNKNOWN."""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["user_query"])
    ]
    
    response = llm.invoke(messages)
    airport_code = response.content.strip().upper()
    
    if airport_code == "UNKNOWN" or not airport_code:
        weather_data = {
            "status": "not_found",
            "message": "No airport found in the query"
        }
    else:
        weather_data = query_airport_weather(airport_code)
    
    print(f"   Airport: {airport_code}")
    print(f"   Status: {weather_data['status']}")
    
    return {
        **state,
        "weather_data": weather_data,
        "messages": [AIMessage(content=f"Weather Expert: Checked METAR for {airport_code}. Status: {weather_data['status']}")],
        "next_agent": "compliance_node",
        "loop_count": state["loop_count"] + 1
    }

# ─────────────────────────────────────────
# AGENT NODE 3: COMPLIANCE & MITIGATION
# ─────────────────────────────────────────

def compliance_node(state: AgentState) -> AgentState:
    print("⚖️  Compliance Node: Evaluating DOT rules...")
    
    llm = get_llm()
    
    # Extract delay minutes from user query
    system_prompt = """You are a DOT compliance expert. Extract the delay duration 
    in minutes from the user's query.
    Convert hours to minutes if needed (e.g. "3 hours" = 180, "3.5 hours" = 210).
    Respond with ONLY a number (e.g. 185).
    If no delay duration is found, respond with 0."""
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=state["user_query"])
    ]
    
    response = llm.invoke(messages)
    
    try:
        delay_minutes = float(response.content.strip())
    except:
        delay_minutes = 0
    
    # Get delay cause from flight data
    flight_data = state.get("flight_data", {})
    summary = flight_data.get("summary", {})
    delay_cause = summary.get("most_common_delay_cause", "unknown")
    
    compliance_data = check_dot_compliance(delay_minutes, delay_cause)
    
    print(f"   Delay minutes: {delay_minutes}")
    print(f"   Legal status: {compliance_data['legal_status']}")
    
    return {
        **state,
        "compliance_data": compliance_data,
        "messages": [AIMessage(content=f"Compliance Node: Evaluated {delay_minutes} minute delay. Legal status: {compliance_data['legal_status']}")],
        "next_agent": "synthesizer",
        "loop_count": state["loop_count"] + 1
    }

# ─────────────────────────────────────────
# AGENT NODE 4: SYNTHESIZER
# ─────────────────────────────────────────

def synthesizer_node(state: AgentState) -> AgentState:
    print("📋 Synthesizer Node: Generating final response...")
    
    llm = get_llm()
    
    flight_data = state.get("flight_data", {})
    weather_data = state.get("weather_data", {})
    compliance_data = state.get("compliance_data", {})
    
    system_prompt = """You are an aviation disruption analyst. Synthesize the 
    provided data into a clear, structured response for the passenger.
    
    Structure your response in three sections:
    1. OBJECTIVE REALITY: What the data actually shows about the delay cause
    2. LEGAL POSITION: DOT compliance status and refund eligibility  
    3. RECOMMENDED ACTION: What the passenger should do next
    
    Be direct and specific. Use the actual data provided."""
    
    user_prompt = f"""
    User Query: {state['user_query']}
    
    Flight History Data:
    {flight_data}
    
    Weather Data:
    {weather_data}
    
    DOT Compliance Data:
    {compliance_data}
    
    Generate a clear, actionable response for the passenger.
    """
    
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt)
    ]
    
    response = llm.invoke(messages)
    
    return {
        **state,
        "final_response": response.content,
        "messages": [AIMessage(content="Synthesizer: Final response generated.")],
        "next_agent": END,
        "loop_count": state["loop_count"] + 1
    }

# ─────────────────────────────────────────
# CIRCUIT BREAKER ROUTER
# ─────────────────────────────────────────

def router(state: AgentState) -> Literal["data_analyst", "weather_expert", "compliance_node", "synthesizer", "__end__"]:
    # Hard stop at 5 loops
    if state["loop_count"] >= 5:
        print("⚠️  Circuit breaker triggered — max loops reached")
        return "__end__"
    
    next_agent = state.get("next_agent", "__end__")
    
    if next_agent == END or next_agent == "__end__":
        return "__end__"
    
    return next_agent

# ─────────────────────────────────────────
# BUILD THE GRAPH
# ─────────────────────────────────────────

def build_agent_graph():
    graph = StateGraph(AgentState)
    
    # Add nodes
    graph.add_node("data_analyst", data_analyst_node)
    graph.add_node("weather_expert", weather_expert_node)
    graph.add_node("compliance_node", compliance_node)
    graph.add_node("synthesizer", synthesizer_node)
    
    # Set entry point
    graph.set_entry_point("data_analyst")
    
    # Add conditional edges from router
    graph.add_conditional_edges("data_analyst", router)
    graph.add_conditional_edges("weather_expert", router)
    graph.add_conditional_edges("compliance_node", router)
    graph.add_conditional_edges("synthesizer", router)
    
    return graph.compile()

# ─────────────────────────────────────────
# RUN FUNCTION
# ─────────────────────────────────────────

def run_agent(user_query: str) -> dict:
    graph = build_agent_graph()
    
    initial_state = {
        "user_query": user_query,
        "messages": [],
        "flight_data": {},
        "weather_data": {},
        "compliance_data": {},
        "next_agent": "data_analyst",
        "loop_count": 0,
        "final_response": ""
    }
    
    result = graph.invoke(initial_state)
    return result