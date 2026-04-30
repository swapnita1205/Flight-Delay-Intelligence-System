-- One-time recovery: rebuild fl_date from year/month/day_of_month.
-- Needed if an earlier ingest run loaded fl_date as NULL because the
-- BTS date format wasn't matched. Safe to run multiple times.
UPDATE flights_raw
SET fl_date = MAKE_DATE(year, month, day_of_month)
WHERE fl_date IS NULL
  AND year IS NOT NULL
  AND month IS NOT NULL
  AND day_of_month IS NOT NULL;

SELECT COUNT(*) AS rows_with_date FROM flights_raw WHERE fl_date IS NOT NULL;
