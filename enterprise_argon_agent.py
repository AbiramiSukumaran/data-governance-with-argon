"""
Argon Autonomous Data Quality Doctor

Use Case: Let Gemini 4 Argon inspect, diagnose, and autonomously generate 
          and run SQL cleaning scripts to repair corrupted warehouse data.
This is for 4 records. If you want to do this for 1M records, use the BigQuery SQL approach from the README.md
"""

import json
import time
from google.cloud import bigquery

PROJECT_ID = "REPLACE_WITH_YOUR_PROJECT_ID"
DATASET_ID = "argon_agent"
LOCATION = "US"
CONNECTION_ID = "ai_connection"
MODEL_NAME = f"{PROJECT_ID}.{DATASET_ID}.argon_frontier_model"

client = bigquery.Client(project=PROJECT_ID, location=LOCATION)

def run_query(query: str, desc: str = "", job_config: bigquery.QueryJobConfig = None):
    print(f"\n[+] Executing: {desc}...")
    job = client.query(query, job_config=job_config)
    result = job.result()
    print(f"[✓] Completed: {desc}")
    return result

def setup_environment():
    """Sets up the dataset, the remote model, and creates a sample messy table."""
    run_query(
        f"CREATE SCHEMA IF NOT EXISTS `{PROJECT_ID}.{DATASET_ID}`;",
        "Create Dataset",
    )

    ddl_model = f"""
    CREATE OR REPLACE MODEL `{MODEL_NAME}`
    REMOTE WITH CONNECTION `{PROJECT_ID}.{LOCATION.lower()}.{CONNECTION_ID}`
    OPTIONS (ENDPOINT = 'gemini-4-argon');
    """
    run_query(ddl_model, "Register Gemini 4 Argon Model")

    # Double braces around the JSON metadata to protect Python string interpolation
    ddl_corrupt_table = f"""
    CREATE OR REPLACE TABLE `{PROJECT_ID}.{DATASET_ID}.messy_transactions` AS (
      SELECT 1 AS tx_id, '2026-10-25 14:30:00 UTC' AS tx_time, '$150.00' AS raw_amount, '{{"customer_id": "C-9902", "status": "COMPLETED"}}' AS metadata
      UNION ALL
      SELECT 2, '25/10/2026 15:45:00 +05:30', '12000.00 INR', 'customer_id: C-1120, status: pending'
      UNION ALL
      SELECT 3, '2026-10-26T09:15:00Z', '€45.50', 'UNKNOWN_USER'
      UNION ALL
      SELECT 4, 'Invalid/Unknown Date', 'FREE_PROMO_CODE', '{{"customer_id": "C-4421", "status": "FAILED_ATTEMPT"}}'
    );
    """
    run_query(ddl_corrupt_table, "Create Corrupt Target Table")

def run_autonomous_data_doctor():
    print(" Pulling raw, corrupted data sample...")
    query_sample = f"SELECT * FROM `{PROJECT_ID}.{DATASET_ID}.messy_transactions` LIMIT 10"
    sample_rows = list(client.query(query_sample).result())
    formatted_sample = [dict(r.items()) for r in sample_rows]

    user_task = f"""
    You are an senior, elite GCP Principal Data Architect. Inspect the raw, heavily corrupted BigQuery table:
    {json.dumps(formatted_sample, indent=2)}

    DIAGNOSTIC & REMEDIATION MANDATE:
    1. Identify all data formatting anomalies across 'tx_time', 'raw_amount', and 'metadata'.
    2. Write a funny, highly technical developer-centric summary of your diagnoses.
    3. Generate a single, production-grade BigQuery SQL query that will output a CLEAN, standardized view.
       The standardized query MUST:
       - Standardize 'tx_time' as a UTC TIMESTAMP (naming it 'clean_time', handling invalid dates by returning NULL).
       - Parse and normalize all 'raw_amount' fields into a standardized FLOAT64 value (naming it 'clean_amount').
         Convert currencies: 1 USD = 84 INR, 1 EUR = 1.08 USD. Convert 'FREE_PROMO_CODE' to 0.0.
       - Safely parse 'metadata', extracting 'customer_id' and 'status'.
       - IMPORTANT: Do not use double escapes inside your SQL regex.

    FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS (USE '===SPLIT===' AS THE SEPARATOR):
    <your diagnostic summary here>
    ===SPLIT===
    SELECT tx_id, ... AS clean_time, ... AS clean_amount, ... AS customer_id, ... AS status FROM `{PROJECT_ID}.{DATASET_ID}.messy_transactions`
    """

    query = f"""
    SELECT result
    FROM AI.GENERATE_TEXT(
      MODEL `{MODEL_NAME}`,
      (SELECT @prompt_param AS prompt),
      STRUCT(0.1 AS temperature, 4096 AS max_output_tokens)
    );
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("prompt_param", "STRING", user_task)]
    )

    start_time = time.time()
    rows = list(run_query(query, "Autonomous Diagnosis & SQL Formulation", job_config=job_config))
    latency = time.time() - start_time
    print(f"[⚡] Argon deep thinking completed in {latency:.2f}s")

    raw_response = rows[0]["result"]
    parts = raw_response.split("===SPLIT===")
    diagnosis_report = parts[0].strip()
    raw_sql = parts[1].split("```sql")[-1].split("```")[0].strip()
    raw_sql = raw_sql.replace("SAFE.CAST", "SAFE_CAST")

    print("" + "=" * 80)
    print("📋 GCP DATA ARCHITECT DIAGNOSIS & REMEDIATION REPORT")
    print("=" * 80)
    print(diagnosis_report)
    print("=" * 80)

    clean_results = run_query(raw_sql, "Materialize Clean Data View")

    print("💎 REPAIRED AND STANDARDIZED DATASETS (Unified Schema):")
    print(f"{'ID':<6} | {'UTC Time':<25} | {'USD Amount':<10} | {'Customer':<10} | {'Status':<10}")
    print("-" * 75)
    for row in clean_results:
        tx_id = str(row.get('tx_id') if row.get('tx_id') is not None else 'NULL')
        clean_time = str(row.get('clean_time') if row.get('clean_time') is not None else 'NULL')
        clean_amt = row.get('clean_amount')
        amt_str = f"${clean_amt:<9.2f}" if clean_amt is not None else "NULL     "
        customer_id = str(row.get('customer_id') if row.get('customer_id') is not None else 'NULL')
        status = str(row.get('status') if row.get('status') is not None else 'NULL')
        print(f"{tx_id:<6} | {clean_time:<25} | {amt_str} | {customer_id:<10} | {status:<10}")

if __name__ == "__main__":
    setup_environment()
    run_autonomous_data_doctor()
