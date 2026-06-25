from agent import run_agent

# ─────────────────────────────────────────
# TEST 1: Non-existent tail number
# ─────────────────────────────────────────

print("\n" + "="*60)
print("TEST 1: Non-existent tail number")
print("="*60)

result = run_agent("My flight on aircraft tail NFAKE99 is delayed 4 hours at Atlanta.")

print("\nFlight data status:", result["flight_data"].get("status"))
print("Final response preview:", result["final_response"][:300])

# ─────────────────────────────────────────
# TEST 2: Unknown airport
# ─────────────────────────────────────────

print("\n" + "="*60)
print("TEST 2: Unknown or misspelled airport")
print("="*60)

result = run_agent("My flight on tail N691CA is delayed 2 hours at XYZABC airport.")

print("\nWeather data status:", result["weather_data"].get("status"))
print("Final response preview:", result["final_response"][:300])

# ─────────────────────────────────────────
# TEST 3: No delay duration mentioned
# ─────────────────────────────────────────

print("\n" + "="*60)
print("TEST 3: No delay duration in query")
print("="*60)

result = run_agent("What is the history of aircraft N691CA?")

print("\nCompliance delay minutes:", result["compliance_data"].get("delay_minutes"))
print("Compliance legal status:", result["compliance_data"].get("legal_status"))
print("Final response preview:", result["final_response"][:300])

# ─────────────────────────────────────────
# TEST 4: Delay below DOT threshold
# ─────────────────────────────────────────

print("\n" + "="*60)
print("TEST 4: Delay below DOT 3-hour threshold")
print("="*60)

result = run_agent("My flight on tail N691CA is delayed 45 minutes at Chicago O'Hare.")

print("\nCompliance legal status:", result["compliance_data"].get("legal_status"))
print("Qualifies for refund:", result["compliance_data"].get("qualifies_for_refund"))
print("Final response preview:", result["final_response"][:300])

# ─────────────────────────────────────────
# TEST 5: Verify circuit breaker
# ─────────────────────────────────────────

print("\n" + "="*60)
print("TEST 5: Circuit breaker loop count verification")
print("="*60)

result = run_agent("My flight on tail N691CA is delayed 3 hours at Chicago O'Hare.")

print("\nTotal loops used:", result["loop_count"])
print("Circuit breaker limit: 5")
print("Circuit breaker safe:", result["loop_count"] <= 5)