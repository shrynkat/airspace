from agent import run_agent

query = """
My flight on aircraft tail N691CA is currently sitting with a 
3 hour and 14 minute delay at Chicago O'Hare (ORD). 
The gate agent says it's due to weather. 
What is the actual status and what are my options?
"""

print("Running agent...\n")
result = run_agent(query)

print("\n" + "="*50)
print("AGENT REASONING STEPS:")
print("="*50)
for message in result["messages"]:
    print(f"  {message.content}")

print("\n" + "="*50)
print("FINAL RESPONSE:")
print("="*50)
print(result["final_response"])