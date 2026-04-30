"""
Load modeling features from the PostgreSQL `flight_features` table.

Returns a clean pandas DataFrame ready for train/test splitting in
`src/train_model.py`.

Weather features (precip_in, visibility_mi, wind_speed_mph) are included
when airport_weather has been populated by src/fetch_weather.py.  Rows
without a weather match are filled with typical-conditions defaults so the
pipeline still works without weather data.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from database import get_engine


# Weather column defaults used when airport_weather rows are absent.
# "no precipitation, good visibility, light wind" represents typical conditions.
WEATHER_DEFAULTS: dict[str, float] = {
    "precip_in": 0.0,
    "visibility_mi": 10.0,
    "wind_speed_mph": 8.0,
}

WEATHER_FEATURES = list(WEATHER_DEFAULTS.keys())

MODEL_COLUMNS = [
    "month",
    "day_of_week",
    "dep_hour",
    "op_unique_carrier",
    "origin",
    "dest",
    "distance",
    "precip_in",
    "visibility_mi",
    "wind_speed_mph",
    "is_arrival_delayed",
]

NUMERIC_FEATURES = ["month", "day_of_week", "dep_hour", "distance"] + WEATHER_FEATURES
CATEGORICAL_FEATURES = ["op_unique_carrier", "origin", "dest"]
TARGET = "is_arrival_delayed"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("features")


def load_features(sample_size: int | None = 500_000) -> pd.DataFrame:
    """
    Load `flight_features` from PostgreSQL.

    Args:
        sample_size: cap the result to this many rows for faster local
            training. Pass `None` to load every row.

    Returns:
        A clean DataFrame ready for modeling.
    """
    engine = get_engine()
    cols = ", ".join(MODEL_COLUMNS)

    if sample_size is not None:
        query = (
            f"SELECT {cols} FROM flight_features "
            f"ORDER BY RANDOM() LIMIT {int(sample_size)}"
        )
    else:
        query = f"SELECT {cols} FROM flight_features"

    log.info("Loading features from PostgreSQL (sample_size=%s)", sample_size)
    df = pd.read_sql(query, con=engine)
    log.info("Loaded %s rows", len(df))

    return clean_for_modeling(df)


BASE_NUMERIC = ["month", "day_of_week", "dep_hour", "distance"]


def clean_for_modeling(df: pd.DataFrame) -> pd.DataFrame:
    """Drop rows missing core features; fill weather NULLs with typical-conditions defaults."""
    required = [TARGET] + CATEGORICAL_FEATURES + BASE_NUMERIC
    df = df.dropna(subset=required).copy()

    df[TARGET] = df[TARGET].astype(int)
    for col in BASE_NUMERIC:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df = df.dropna(subset=BASE_NUMERIC)

    # Weather columns are NULL when airport_weather hasn't been populated yet.
    # Fill with typical-conditions defaults so the pipeline works regardless.
    for col, default in WEATHER_DEFAULTS.items():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(default)
        else:
            df[col] = default

    log.info("Clean dataset shape: %s", df.shape)
    return df


if __name__ == "__main__":
    sample = load_features(sample_size=10_000)
    print(sample.head())
    print(sample[TARGET].value_counts(normalize=True))
