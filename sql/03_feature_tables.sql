-- =============================================================================
-- 03_feature_tables.sql
-- Builds the flight_features table consumed by the ML pipeline.
-- Run after sql/02_cleaning_views.sql.
-- =============================================================================

TRUNCATE TABLE flight_features;

-- -----------------------------------------------------------------------------
-- One row per flight with the columns used for modeling and Tableau.
-- The `route` column (origin-dest) is added for easy slicing in dashboards.
-- -----------------------------------------------------------------------------
-- Left-join airport_weather so flights without a matched observation still
-- appear in flight_features (weather cols will be NULL until fetch_weather.py
-- has been run for the relevant airports and dates).
INSERT INTO flight_features (
    flight_date,
    month,
    day_of_week,
    dep_hour,
    op_unique_carrier,
    origin,
    dest,
    distance,
    cancelled,
    dep_delay,
    arr_delay,
    is_arrival_delayed,
    carrier_delay,
    weather_delay,
    nas_delay,
    security_delay,
    late_aircraft_delay,
    route,
    precip_in,
    visibility_mi,
    wind_speed_mph
)
SELECT
    fc.flight_date,
    fc.month,
    fc.day_of_week,
    fc.dep_hour,
    fc.op_unique_carrier,
    fc.origin,
    fc.dest,
    fc.distance,
    fc.cancelled,
    fc.dep_delay,
    fc.arr_delay,
    fc.is_arrival_delayed,
    fc.carrier_delay,
    fc.weather_delay,
    fc.nas_delay,
    fc.security_delay,
    fc.late_aircraft_delay,
    fc.origin || '-' || fc.dest AS route,
    aw.precip_in,
    aw.visibility_mi,
    aw.wind_speed_mph
FROM flights_clean fc
LEFT JOIN airport_weather aw
    ON  aw.airport_code = fc.origin
    AND aw.obs_date     = fc.flight_date
    AND aw.obs_hour     = fc.dep_hour;

SELECT COUNT(*) AS feature_row_count FROM flight_features;
