import pandas as pd
from google.cloud import bigquery
import os

# Point to your credentials
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "credentials.json"

# Config
PROJECT_ID = "airspace-platform"
DATASET_ID = "airspace_raw"
TABLE_ID = "flights_raw"

# Load CSV
print("Loading CSV...")
df = pd.read_csv("data/flights_raw.csv")

# Clean column names — BigQuery doesn't allow spaces
df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

# Drop rows with no tail number — useless for lineage tracking
df = df.dropna(subset=["tail_num"])

# Ensure delay columns are numeric
delay_cols = ["dep_delay", "arr_delay", "carrier_delay", "weather_delay", "nas_delay"]
for col in delay_cols:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")

print(f"Rows after cleaning: {len(df)}")

# Upload to BigQuery
client = bigquery.Client(project=PROJECT_ID)

table_ref = f"{PROJECT_ID}.{DATASET_ID}.{TABLE_ID}"

job_config = bigquery.LoadJobConfig(
    write_disposition="WRITE_TRUNCATE",  # Overwrites table if it already exists
    autodetect=True                      # BigQuery figures out the schema automatically
)

print("Uploading to BigQuery...")
job = client.load_table_from_dataframe(df, table_ref, job_config=job_config)
job.result()  # Wait for it to finish

table = client.get_table(table_ref)
print(f"Done. {table.num_rows} rows loaded into {table_ref}")