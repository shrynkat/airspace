from tools import query_flight_history, query_airport_weather, check_dot_compliance

print("=== Testing Flight History Tool ===")
result = query_flight_history("N691CA", limit=3)
print(f"Status: {result['status']}")
print(f"Records found: {result['total_records_returned']}")
print(f"Summary: {result['summary']}")

print("\n=== Testing Weather Tool ===")
weather = query_airport_weather("KORD")
print(f"Status: {weather['status']}")
print(f"Airport: {weather['airport']}")
print(f"Flight rules: {weather['flight_rules']}")
print(f"Raw METAR: {weather['raw_metar']}")

print("\n=== Testing DOT Compliance Tool ===")
compliance = check_dot_compliance(185, "carrier_controlled")
print(f"Legal status: {compliance['legal_status']}")
print(f"Recommendation: {compliance['recommendation']}")