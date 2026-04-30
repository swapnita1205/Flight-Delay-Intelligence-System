-- =============================================================================
-- 04_analytics_queries.sql
-- Portfolio-friendly analytics queries powering the Tableau dashboard.
-- Source: flight_features (one row per flight).
-- =============================================================================

-- -----------------------------------------------------------------------------
-- 1. Delay rate by airline.
--    What share of each carrier's flights arrive 15+ minutes late?
-- -----------------------------------------------------------------------------
SELECT
    op_unique_carrier                                            AS airline,
    COUNT(*)                                                     AS total_flights,
    SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END)          AS delayed_flights,
    ROUND(
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS delay_rate_pct
FROM flight_features
GROUP BY op_unique_carrier
ORDER BY delay_rate_pct DESC;


-- -----------------------------------------------------------------------------
-- 2. Delay rate by origin airport.
--    Which airports send out the most delayed flights?
-- -----------------------------------------------------------------------------
SELECT
    origin                                                       AS origin_airport,
    COUNT(*)                                                     AS total_flights,
    ROUND(
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS delay_rate_pct,
    ROUND(AVG(arr_delay)::NUMERIC, 2)                            AS avg_arr_delay_min
FROM flight_features
GROUP BY origin
ORDER BY delay_rate_pct DESC;


-- -----------------------------------------------------------------------------
-- 3. Average delay by hour of day.
--    Helps answer: "Should I take the morning or evening flight?"
-- -----------------------------------------------------------------------------
SELECT
    dep_hour,
    COUNT(*)                                                     AS total_flights,
    ROUND(AVG(arr_delay)::NUMERIC, 2)                            AS avg_arr_delay_min,
    ROUND(
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS delay_rate_pct
FROM flight_features
GROUP BY dep_hour
ORDER BY dep_hour;


-- -----------------------------------------------------------------------------
-- 4. Delay rate by day of week (1 = Monday ... 7 = Sunday in BTS data).
-- -----------------------------------------------------------------------------
SELECT
    day_of_week,
    COUNT(*)                                                     AS total_flights,
    ROUND(
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS delay_rate_pct
FROM flight_features
GROUP BY day_of_week
ORDER BY day_of_week;


-- -----------------------------------------------------------------------------
-- 5. Delay cause breakdown.
--    Total minutes attributed to each delay reason across all flights.
-- -----------------------------------------------------------------------------
SELECT
    'carrier'        AS delay_cause, ROUND(SUM(carrier_delay)::NUMERIC, 0)        AS total_minutes FROM flight_features
UNION ALL
SELECT
    'weather',                       ROUND(SUM(weather_delay)::NUMERIC, 0)        FROM flight_features
UNION ALL
SELECT
    'nas',                           ROUND(SUM(nas_delay)::NUMERIC, 0)            FROM flight_features
UNION ALL
SELECT
    'security',                      ROUND(SUM(security_delay)::NUMERIC, 0)       FROM flight_features
UNION ALL
SELECT
    'late_aircraft',                 ROUND(SUM(late_aircraft_delay)::NUMERIC, 0)  FROM flight_features
ORDER BY total_minutes DESC;


-- -----------------------------------------------------------------------------
-- 6. Top 20 worst routes by delay rate (only routes with >= 100 flights).
--    Filtering by volume avoids tiny / noisy routes.
-- -----------------------------------------------------------------------------
SELECT
    route,
    COUNT(*)                                                     AS total_flights,
    ROUND(
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS delay_rate_pct,
    ROUND(AVG(arr_delay)::NUMERIC, 2)                            AS avg_arr_delay_min
FROM flight_features
GROUP BY route
HAVING COUNT(*) >= 100
ORDER BY delay_rate_pct DESC
LIMIT 20;


-- -----------------------------------------------------------------------------
-- 7. Monthly delay trend.
--    Useful for line charts in Tableau showing seasonality.
-- -----------------------------------------------------------------------------
SELECT
    DATE_TRUNC('month', flight_date)::DATE                       AS month_start,
    COUNT(*)                                                     AS total_flights,
    ROUND(
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS delay_rate_pct,
    ROUND(AVG(arr_delay)::NUMERIC, 2)                            AS avg_arr_delay_min
FROM flight_features
GROUP BY DATE_TRUNC('month', flight_date)
ORDER BY month_start;


-- -----------------------------------------------------------------------------
-- 8. Cancellation rate by airline.
-- -----------------------------------------------------------------------------
SELECT
    op_unique_carrier                                            AS airline,
    COUNT(*)                                                     AS total_flights,
    SUM(CASE WHEN cancelled THEN 1 ELSE 0 END)                   AS cancelled_flights,
    ROUND(
        100.0 * SUM(CASE WHEN cancelled THEN 1 ELSE 0 END) / COUNT(*),
        2
    )                                                            AS cancellation_rate_pct
FROM flight_features
GROUP BY op_unique_carrier
ORDER BY cancellation_rate_pct DESC;


-- -----------------------------------------------------------------------------
-- 9. Window function: rank airlines by monthly delay rate.
--    Within each month, rank carriers from worst to best.
-- -----------------------------------------------------------------------------
WITH monthly AS (
    SELECT
        DATE_TRUNC('month', flight_date)::DATE                   AS month_start,
        op_unique_carrier                                        AS airline,
        COUNT(*)                                                 AS total_flights,
        ROUND(
            100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*),
            2
        )                                                        AS delay_rate_pct
    FROM flight_features
    GROUP BY 1, 2
)
SELECT
    month_start,
    airline,
    total_flights,
    delay_rate_pct,
    RANK() OVER (
        PARTITION BY month_start
        ORDER BY delay_rate_pct DESC
    )                                                            AS delay_rank
FROM monthly
ORDER BY month_start, delay_rank;


-- -----------------------------------------------------------------------------
-- 10. CTE: airports with above-average delay rate.
--     Compares each origin's delay rate to the network-wide average.
-- -----------------------------------------------------------------------------
WITH airport_stats AS (
    SELECT
        origin,
        COUNT(*)                                                 AS total_flights,
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*) AS delay_rate_pct
    FROM flight_features
    GROUP BY origin
),
overall AS (
    SELECT
        100.0 * SUM(CASE WHEN is_arrival_delayed THEN 1 ELSE 0 END) / COUNT(*) AS avg_delay_rate_pct
    FROM flight_features
)
SELECT
    a.origin,
    a.total_flights,
    ROUND(a.delay_rate_pct::NUMERIC, 2)                          AS delay_rate_pct,
    ROUND(o.avg_delay_rate_pct::NUMERIC, 2)                      AS network_avg_pct,
    ROUND((a.delay_rate_pct - o.avg_delay_rate_pct)::NUMERIC, 2) AS pct_points_above_avg
FROM airport_stats a
CROSS JOIN overall o
WHERE a.delay_rate_pct > o.avg_delay_rate_pct
  AND a.total_flights >= 500
ORDER BY pct_points_above_avg DESC;
