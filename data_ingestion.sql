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
