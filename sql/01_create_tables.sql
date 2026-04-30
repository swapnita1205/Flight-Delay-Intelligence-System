-- =============================================================================
-- 01_create_tables.sql
-- Defines the four core tables for the Flight Delay Intelligence project.
-- Run once before ingesting any data.
-- =============================================================================

-- -----------------------------------------------------------------------------
-- flights_raw: landing zone for the BTS On-Time Performance CSV files.
-- Columns mirror the source CSV (lowercase snake_case).
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS flights_raw CASCADE;
CREATE TABLE flights_raw (
    year                 INTEGER,
    month                INTEGER,
    day_of_month         INTEGER,
    day_of_week          INTEGER,
    fl_date              DATE,
    op_unique_carrier    VARCHAR(5),
    origin               VARCHAR(5),
    dest                 VARCHAR(5),
    crs_dep_time         INTEGER,
    dep_time             INTEGER,
    dep_delay            DOUBLE PRECISION,
    crs_arr_time         INTEGER,
    arr_time             INTEGER,
    arr_delay            DOUBLE PRECISION,
    cancelled            DOUBLE PRECISION,
    cancellation_code    VARCHAR(2),
    diverted             DOUBLE PRECISION,
    air_time             DOUBLE PRECISION,
    distance             DOUBLE PRECISION,
    carrier_delay        DOUBLE PRECISION,
    weather_delay        DOUBLE PRECISION,
    nas_delay            DOUBLE PRECISION,
    security_delay       DOUBLE PRECISION,
    late_aircraft_delay  DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_flights_raw_fl_date ON flights_raw (fl_date);
CREATE INDEX IF NOT EXISTS idx_flights_raw_carrier ON flights_raw (op_unique_carrier);

-- -----------------------------------------------------------------------------
-- flights_clean: cleaned, validated, analytics-ready flights.
-- Populated by sql/02_cleaning_views.sql.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS flights_clean CASCADE;
CREATE TABLE flights_clean (
    flight_date           DATE,
    year                  INTEGER,
    month                 INTEGER,
    day_of_month          INTEGER,
    day_of_week           INTEGER,
    op_unique_carrier     VARCHAR(5),
    origin                VARCHAR(5),
    dest                  VARCHAR(5),
    crs_dep_time          INTEGER,
    dep_hour              INTEGER,
    dep_time              INTEGER,
    dep_delay             DOUBLE PRECISION,
    crs_arr_time          INTEGER,
    arr_hour              INTEGER,
    arr_time              INTEGER,
    arr_delay             DOUBLE PRECISION,
    cancelled             BOOLEAN,
    cancellation_code     VARCHAR(2),
    air_time              DOUBLE PRECISION,
    distance              DOUBLE PRECISION,
    carrier_delay         DOUBLE PRECISION,
    weather_delay         DOUBLE PRECISION,
    nas_delay             DOUBLE PRECISION,
    security_delay        DOUBLE PRECISION,
    late_aircraft_delay   DOUBLE PRECISION,
    is_arrival_delayed    BOOLEAN,
    is_departure_delayed  BOOLEAN
);

CREATE INDEX IF NOT EXISTS idx_flights_clean_date    ON flights_clean (flight_date);
CREATE INDEX IF NOT EXISTS idx_flights_clean_carrier ON flights_clean (op_unique_carrier);
CREATE INDEX IF NOT EXISTS idx_flights_clean_origin  ON flights_clean (origin);

-- -----------------------------------------------------------------------------
-- airport_weather: hourly weather observations per airport.
-- Populated by src/fetch_weather.py (NOAA CDO API).
-- Joined into flight_features by sql/03_feature_tables.sql.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS airport_weather CASCADE;
CREATE TABLE airport_weather (
    airport_code    VARCHAR(5)        NOT NULL,
    obs_date        DATE              NOT NULL,
    obs_hour        INTEGER           NOT NULL,  -- 0-23 local time
    precip_in       DOUBLE PRECISION,            -- hourly precipitation (inches)
    visibility_mi   DOUBLE PRECISION,            -- visibility (statute miles)
    wind_speed_mph  DOUBLE PRECISION,            -- sustained wind speed (mph)
    PRIMARY KEY (airport_code, obs_date, obs_hour)
);

CREATE INDEX IF NOT EXISTS idx_weather_airport_date ON airport_weather (airport_code, obs_date);

-- -----------------------------------------------------------------------------
-- flight_features: one row per flight, ready for the ML pipeline.
-- Populated by sql/03_feature_tables.sql.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS flight_features CASCADE;
CREATE TABLE flight_features (
    flight_date           DATE,
    month                 INTEGER,
    day_of_week           INTEGER,
    dep_hour              INTEGER,
    op_unique_carrier     VARCHAR(5),
    origin                VARCHAR(5),
    dest                  VARCHAR(5),
    distance              DOUBLE PRECISION,
    cancelled             BOOLEAN,
    dep_delay             DOUBLE PRECISION,
    arr_delay             DOUBLE PRECISION,
    is_arrival_delayed    BOOLEAN,
    carrier_delay         DOUBLE PRECISION,
    weather_delay         DOUBLE PRECISION,
    nas_delay             DOUBLE PRECISION,
    security_delay        DOUBLE PRECISION,
    late_aircraft_delay   DOUBLE PRECISION,
    route                 VARCHAR(15),
    -- Joined from airport_weather (NULL when weather data not yet fetched)
    precip_in             DOUBLE PRECISION,
    visibility_mi         DOUBLE PRECISION,
    wind_speed_mph        DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_flight_features_date  ON flight_features (flight_date);
CREATE INDEX IF NOT EXISTS idx_flight_features_route ON flight_features (route);

-- -----------------------------------------------------------------------------
-- delay_predictions: model output, consumed by Tableau.
-- Populated by src/save_predictions.py.
-- -----------------------------------------------------------------------------
DROP TABLE IF EXISTS delay_predictions CASCADE;
CREATE TABLE delay_predictions (
    flight_date                  DATE,
    op_unique_carrier            VARCHAR(5),
    origin                       VARCHAR(5),
    dest                         VARCHAR(5),
    route                        VARCHAR(15),
    month                        INTEGER,
    day_of_week                  INTEGER,
    dep_hour                     INTEGER,
    distance                     DOUBLE PRECISION,
    actual_is_delayed            BOOLEAN,
    predicted_is_delayed         BOOLEAN,
    predicted_delay_probability  DOUBLE PRECISION
);

CREATE INDEX IF NOT EXISTS idx_predictions_date  ON delay_predictions (flight_date);
CREATE INDEX IF NOT EXISTS idx_predictions_route ON delay_predictions (route);
