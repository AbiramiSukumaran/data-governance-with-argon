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
