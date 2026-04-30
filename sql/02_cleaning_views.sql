-- =============================================================================
-- 02_cleaning_views.sql
-- Cleans flights_raw into the analytics-ready flights_clean table.
-- Run after sql/01_create_tables.sql and src/ingest.py.
-- =============================================================================

TRUNCATE TABLE flights_clean;

-- -----------------------------------------------------------------------------
-- Insert cleaned, validated flights into flights_clean.
-- Filters out diverted flights and unrealistic / corrupt rows.
-- Adds engineered fields: flight_date, dep_hour, arr_hour, delay flags.
-- -----------------------------------------------------------------------------
INSERT INTO flights_clean (
    flight_date,
    year,
    month,
    day_of_month,
    day_of_week,
    op_unique_carrier,
    origin,
    dest,
    crs_dep_time,
    dep_hour,
    dep_time,
    dep_delay,
    crs_arr_time,
    arr_hour,
    arr_time,
    arr_delay,
    cancelled,
    cancellation_code,
    air_time,
    distance,
    carrier_delay,
    weather_delay,
    nas_delay,
    security_delay,
    late_aircraft_delay,
    is_arrival_delayed,
    is_departure_delayed
)
SELECT
    fl_date                                              AS flight_date,
    year,
    month,
    day_of_month,
    day_of_week,
    op_unique_carrier,
    origin,
    dest,
    crs_dep_time,
    -- dep_hour: hour of day, derived from CRS departure time (HHMM int)
    FLOOR(COALESCE(crs_dep_time, 0) / 100)::INT          AS dep_hour,
    dep_time,
    dep_delay,
    crs_arr_time,
    FLOOR(COALESCE(crs_arr_time, 0) / 100)::INT          AS arr_hour,
    arr_time,
    arr_delay,
    -- standardize cancelled as a boolean
    (COALESCE(cancelled, 0) = 1)                         AS cancelled,
    cancellation_code,
    air_time,
    distance,
    -- replace null delay reason columns with 0
    COALESCE(carrier_delay,       0)                     AS carrier_delay,
    COALESCE(weather_delay,       0)                     AS weather_delay,
    COALESCE(nas_delay,           0)                     AS nas_delay,
    COALESCE(security_delay,      0)                     AS security_delay,
    COALESCE(late_aircraft_delay, 0)                     AS late_aircraft_delay,
    (COALESCE(arr_delay, 0) >= 15)                       AS is_arrival_delayed,
    (COALESCE(dep_delay, 0) >= 15)                       AS is_departure_delayed
FROM flights_raw
WHERE
    COALESCE(diverted, 0) = 0          -- non-diverted flights only
    AND distance IS NOT NULL
    AND distance > 0
    AND month BETWEEN 1 AND 12
    AND day_of_week BETWEEN 1 AND 7
    AND fl_date IS NOT NULL
    AND op_unique_carrier IS NOT NULL
    AND origin IS NOT NULL
    AND dest IS NOT NULL;

-- Quick sanity check: how many rows landed in flights_clean.
SELECT COUNT(*) AS clean_row_count FROM flights_clean;
