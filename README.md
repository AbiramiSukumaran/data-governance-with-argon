Let us walk through the complete, end-to-end engineering implementation to provision the infrastructure, register Gemini 4 Argon as a remote model in BigQuery, ingest 1,000,000 corrupted transaction records, and execute the autonomous self-healing pipeline in both Python and native BigQuery Procedural SQL (PL/SQL).

#### **Step 1: Enable the Required Google Cloud APIs**

First, open your Google Cloud Shell terminal and enable the BigQuery, BigQuery Connection, and Agent Platform (previously Vertex AI) APIs so BigQuery can provision Cloud Resource Connections and invoke Gemini 4 Argon endpoints:

&nbsp;

```sh
gcloud services enable \
 bigquery.googleapis.com \
 bigqueryconnection.googleapis.com \
 aiplatform.googleapis.com
```

&nbsp;

#### **Step 2: Configure IAM Permissions for the BigQuery Connection Service Account**

When BigQuery invokes a remote model on Agent Platform, it authenticates using a Google-managed Service Account tied to your BigQuery Cloud Resource Connection.&nbsp;

&nbsp;

```sh
bq mk --connection --location=US --project_id=<<YOUR_PROJECT_ID>> --connection_type=CLOUD_RESOURCE ai_connection
```

&nbsp;

Once it is created, you should be able to retrieve the service account associated with it. That Service Account must hold the role (roles/aiplatform.user). After creating your connection , retrieve its serviceAccountId via bq show and bind the IAM policy:

&nbsp;

```sh
# Inspect the connection to retrieve the generated Service Account email
bq show --connection --location=us <<YOUR_PROJECT_ID>>.us.ai_connection

# Grant Vertex AI User role to the connection's Service Account
gcloud projects add-iam-policy-binding <<YOUR_PROJECT_ID>> \
 --member="serviceAccount:<YOUR_CONNECTION_SERVICE_ACCOUNT_EMAIL>" \
 --role="roles/aiplatform.user"
```

Wait for a few minutes for the permission to propagate.

#### **Step 3: Retrieve and Set Your Google Cloud Project ID**

Verify that your active gcloud environment points to your target and export the environment variables used across CLI and SDK workflows:

&nbsp;

```sh
export PROJECT_ID=$(gcloud config get-value project)
echo "Active Project ID: ${PROJECT_ID}"
```

&nbsp;

#### **Step 4: Create the BigQuery Dataset**

Create a dedicated dataset named enterprise\_argon\_agent in the US multi-region to house the remote model definition, the raw corrupted ingestion tables, and the remediated production tables. To run this open [BigQuery](https://console.cloud.google.com/bigquery) in your Google Cloud Console, navigate to **Studio** and open a new **SQL Query** tab:

&nbsp;

```sql
CREATE SCHEMA IF NOT EXISTS enterprise_argon_agent OPTIONS (location = 'US');
```

&nbsp;

#### **Step 5: Register the Gemini 4 Argon Remote Model**

If you have not yet created the Cloud Resource Connection (ai\_connection), create it via the bq CLI or the Python google-cloud-bigquery-connection SDK, and then execute the CREATE OR REPLACE MODEL DDL statement in BigQuery pointing directly to ENDPOINT \= ‘gemini-4-argon’:

&nbsp;

```sql
CREATE OR REPLACE MODEL `enterprise_argon_agent.argon_frontier_model`
REMOTE WITH CONNECTION `us.ai_connection`
OPTIONS (ENDPOINT = 'gemini-4-argon');
```

&nbsp;

#### **Step 6: Create Target Tables and Ingest 1,000,000 Corrupted Records**

To validate both functional accuracy and planet-scale throughput, we first create a 4-row prototype table (messy\_transactions) that isolates our three primary corruption vectors, followed by a 1,000,000-row table (messy\_transactions\_1m) synthesized in-warehouse via UNNEST(GENERATE\_ARRAY(1, 1000000)):

* Temporal Chaos (**tx\_time**): Mixes standard UTC strings (‘2026–10–25 14:30:00 UTC’), localized DD/MM/YYYY strings with explicit \+05:30 offsets (‘25/10/2026 15:45:00 \+05:30’), ISO-8601 Zulu timestamps (‘2026–10–26T09:15:00Z’), and unparseable sentinel literals (‘Invalid/Unknown Date’).  
* Monetary Denormalization (**raw\_amount**): Couples currency presentation with numeric values across USD (‘\$150.00’), Indian Rupees (‘12000.00 INR’), Euros (‘€45.50’), and zero-value promotional flags (‘FREE\_PROMO\_CODE’).  
* Polymorphic Serialization Failure (**metadata**): Alternates between valid JSON payloads (‘{“customer\_id”: “C-9902”, “status”: “COMPLETED”}’), unquoted YAML-style key-value text (‘customer\_id: C-1120, status: pending’), and missing-data tokens (‘UNKNOWN\_USER’).

&nbsp;

```sql
-- 1,000,000-Row Corrupted Table Generated In-Warehouse

CREATE OR REPLACE TABLE `enterprise_argon_agent.messy_transactions_1m` AS
WITH raw_generator AS (
 SELECT
   idx AS tx_id,
   MOD(idx, 4) AS time_corruption_type,
   MOD(idx, 4) AS amount_corruption_type,
   MOD(idx, 3) AS meta_corruption_type
 FROM
   UNNEST(GENERATE_ARRAY(1, 1000000)) AS idx
)
SELECT
 tx_id,
 CASE time_corruption_type
   WHEN 0 THEN '2026-10-25 14:30:00 UTC'
   WHEN 1 THEN '25/10/2026 15:45:00 +05:30'
   WHEN 2 THEN '2026-10-26T09:15:00Z'
   ELSE 'Invalid/Unknown Date'
 END AS tx_time,
 CASE amount_corruption_type
   WHEN 0 THEN CONCAT('$', CAST(ROUND(10 + (RAND() * 500), 2) AS STRING))
   WHEN 1 THEN CONCAT(CAST(ROUND(500 + (RAND() * 50000), 2) AS STRING), ' INR')
   WHEN 2 THEN CONCAT('€', CAST(ROUND(15 + (RAND() * 300), 2) AS STRING))
   ELSE 'FREE_PROMO_CODE'
 END AS raw_amount,
 CASE meta_corruption_type
   WHEN 0 THEN FORMAT('{"customer_id": "C-%d", "status": "COMPLETED"}', CAST(1000 + MOD(tx_id, 9000) AS INT64))
   WHEN 1 THEN FORMAT('customer_id: C-%d, status: pending', CAST(1000 + MOD(tx_id, 9000) AS INT64))
   ELSE 'UNKNOWN_USER'
 END AS metadata
FROM raw_generator;
```

&nbsp;

#### **Step 7: Execute the Procedural SQL (PL/SQL) and Python Orchestrator in BigQuery**

When building production agentic pipelines with AI.GENERATE\_TEXT, four critical engineering lessons ensure zero-crash execution:

**Modern AI.GENERATE\_TEXT Schema:&nbsp;**

Unlike legacy ML.GENERATE\_TEXT (which outputs ml\_generate\_text\_result), modern AI.GENERATE\_TEXT outputs the generated response in a column named result. Note also that [Gemini 4 Argon](https://ai.google.dev/gemini-api/docs/generate-content/latest-model) ignores legacy sampling parameters (temperature, top\_p, top\_k) on direct API calls in favor of its internal reasoning harness, while BigQuery’s AI.GENERATE\_TEXT wrapper cleanly handles the request payload.

**Parameterized Prompt Binding:&nbsp;**

Passing prompts containing quotes, regex patterns, and JSON blocks via ScalarQueryParameter(“@prompt\_param”) in Python — or FORMAT(“%s”, TO\_JSON\_STRING(…)) in BigQuery Procedural SQL — eliminates SQL string-literal escaping bugs.

**Delimiter-Separated Stream Parsing (===SPLIT===):&nbsp;**

Asking an LLM to wrap SQL containing regular expressions (like r’\[0–9.\]+’ or r’customer\_id:\\s\*(\[^,\\s\]+)’) inside a JSON string often triggers JSONDecodeError due to unescaped backslashes. Using a deterministic plain-text delimiter (===SPLIT===) bypasses JSON escaping traps entirely.

**In-Flight Dialect Sanitization:&nbsp;**

Advanced models occasionally conflate SAFE.PARSE\_TIMESTAMP with SAFE.CAST. Applying an in-flight string replacement (REPLACE(healing\_sql, ‘SAFE.CAST’, ‘SAFE\_CAST’)) guarantees valid BigQuery Standard SQL execution.

Below is the complete, self-contained BigQuery Procedural SQL (PL/SQL) script that samples the 1,000,000-row table, invokes Gemini 4 Argon to synthesize the remediation query, executes it via EXECUTE IMMEDIATE across all 1,000,000 rows, and computes validation metrics:

&nbsp;

````sql
-- =====================================================================
-- Autonomous Data Quality Doctor: Scaling to 1,000,000 Rows
-- =====================================================================
DECLARE prompt_payload STRING;
DECLARE raw_model_response STRING;
DECLARE diagnostic_report STRING;
DECLARE healing_sql STRING;

-- 1. Sample the 1,000,000 row table to give Argon structural context
SET prompt_payload = (
 SELECT FORMAT("""
   You are an elite GCP Principal Data Architect. Inspect a sample of our 1,000,000-row corrupted table:
   %s
  
   DIAGNOSTIC & REMEDIATION MANDATE:
   1. Identify all data formatting anomalies across 'tx_time', 'raw_amount', and 'metadata'.
   2. Write an arrogant, highly technical developer-centric summary of your diagnoses.
   3. Generate a single, production-grade BigQuery SQL query that writes into a new table:
      `enterprise_argon_agent.clean_transactions_1m`.
      The standardized query MUST:
      - Standardize 'tx_time' as a UTC TIMESTAMP (naming it 'clean_time', handling invalid dates by returning NULL).
      - Parse and normalize all 'raw_amount' fields into a standardized FLOAT64 value (naming it 'clean_amount').
        Convert currencies: 1 USD = 84 INR, 1 EUR = 1.08 USD. Convert 'FREE_PROMO_CODE' to 0.0.
      - Safely parse 'metadata', extracting 'customer_id' and 'status'.
  
   FORMAT YOUR RESPONSE EXACTLY AS FOLLOWS (USE '===SPLIT===' AS THE SEPARATOR):
   <your diagnostic summary here>
   ===SPLIT===
   CREATE OR REPLACE TABLE `enterprise_argon_agent.clean_transactions_1m` AS
   SELECT tx_id, ... AS clean_time, ... AS clean_amount, ... AS customer_id, ... AS status
   FROM `enterprise_argon_agent.messy_transactions_1m`
   """,
   (
     SELECT TO_JSON_STRING(ARRAY_AGG(STRUCT(tx_id, tx_time, raw_amount, metadata)))
     FROM (
       SELECT tx_id, tx_time, raw_amount, metadata
       FROM `enterprise_argon_agent.messy_transactions_1m`
       LIMIT 10
     )
   )
 )
);

-- 2. Let Gemini 4 Argon compile the vectorized transformation
SET raw_model_response = (
 SELECT result
 FROM AI.GENERATE_TEXT(
   MODEL `enterprise_argon_agent.argon_frontier_model`,
   (SELECT prompt_payload AS prompt),
   STRUCT(
     0.1 AS temperature,
     4096 AS max_output_tokens
   )
 )
);

-- 3. Parse and sanitize the generated SQL
SET diagnostic_report = SPLIT(raw_model_response, '===SPLIT===')[OFFSET(0)];
SET healing_sql = SPLIT(raw_model_response, '===SPLIT===')[OFFSET(1)];
SET healing_sql = REGEXP_REPLACE(healing_sql, r'^```sql\s*', '');
SET healing_sql = REGEXP_REPLACE(healing_sql, r'\s*```$', '');
SET healing_sql = REPLACE(healing_sql, 'SAFE.CAST', 'SAFE_CAST');

-- 4. Print the Architectural Report
SELECT TRIM(diagnostic_report) AS gcp_architect_diagnostic_report;

-- 5. Execute the compiled SQL query across all 1,000,000 rows in BigQuery!
EXECUTE IMMEDIATE healing_sql;

-- 6. Verify row count and validation metrics of the healed dataset
SELECT
 COUNT(*) AS total_rows_processed,
 COUNT(clean_time) AS valid_utc_timestamps,
 COUNTIF(clean_time IS NULL) AS quarantined_invalid_dates,
 ROUND(AVG(clean_amount), 2) AS average_amount_usd,
 COUNTIF(status = 'COMPLETED') AS total_completed_transactions
FROM `enterprise_argon_agent.clean_transactions_1m`;

-- 7. Verify healed data
select * from enterprise_argon_agent.clean_transactions_1m  where clean_time is not null AND
customer_id is not null and status is not null limit 10000;
````

&nbsp;

&nbsp;
