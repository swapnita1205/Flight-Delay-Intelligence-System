"""
Generate predictions for recent flights and save them to PostgreSQL.

Steps:
    1. Load the trained model from reports/best_delay_model.joblib.
    2. Pull the most recent rows from `flight_features`.
    3. Predict the probability and binary label for each flight.
    4. Write the result to the `delay_predictions` table.

Usage:
    python src/save_predictions.py
"""

from __future__ import annotations

import json
import logging

import joblib
import pandas as pd

from config import METRICS_PATH, MODEL_PATH
from database import get_engine
from features import CATEGORICAL_FEATURES, NUMERIC_FEATURES


PREDICTION_LIMIT = 200_000

OUTPUT_COLUMNS = [
    "flight_date",
    "op_unique_carrier",
    "origin",
    "dest",
    "route",
    "month",
    "day_of_week",
    "dep_hour",
    "distance",
    "actual_is_delayed",
    "predicted_is_delayed",
    "predicted_delay_probability",
]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("save_predictions")


def load_recent_flights(engine, limit: int = PREDICTION_LIMIT) -> pd.DataFrame:
    """Pull the most recent N flights for scoring."""
    query = f"""
        SELECT
            flight_date,
            op_unique_carrier,
            origin,
            dest,
            route,
            month,
            day_of_week,
            dep_hour,
            distance,
            COALESCE(precip_in,      0.0)  AS precip_in,
            COALESCE(visibility_mi,  10.0) AS visibility_mi,
            COALESCE(wind_speed_mph, 8.0)  AS wind_speed_mph,
            is_arrival_delayed
        FROM flight_features
        WHERE flight_date IS NOT NULL
        ORDER BY flight_date DESC
        LIMIT {int(limit)}
    """
    log.info("Loading up to %s recent flights from PostgreSQL", limit)
    df = pd.read_sql(query, con=engine)
    log.info("Loaded %s rows", len(df))
    return df


def load_optimal_threshold() -> float:
    """Read the decision threshold tuned during training from metrics.json."""
    if not METRICS_PATH.exists():
        return 0.5
    payload = json.loads(METRICS_PATH.read_text())
    best_name = payload.get("best_model", "")
    threshold = payload.get("metrics", {}).get(best_name, {}).get("threshold", 0.5)
    return float(threshold)


def predict(df: pd.DataFrame, model, threshold: float = 0.5) -> pd.DataFrame:
    """Add predicted_delay_probability + predicted_is_delayed columns."""
    feature_cols = NUMERIC_FEATURES + CATEGORICAL_FEATURES
    df = df.dropna(subset=feature_cols).copy()

    X = df[feature_cols]

    df["predicted_delay_probability"] = model.predict_proba(X)[:, 1]
    df["predicted_is_delayed"] = (df["predicted_delay_probability"] >= threshold)
    df["actual_is_delayed"] = df["is_arrival_delayed"].astype("boolean")

    return df[OUTPUT_COLUMNS]


def save_to_postgres(df: pd.DataFrame, engine) -> None:
    """Replace the contents of delay_predictions with the latest scoring run."""
    log.info("Writing %s rows to delay_predictions", len(df))
    df.to_sql(
        "delay_predictions",
        con=engine,
        if_exists="replace",
        index=False,
        chunksize=50_000,
        method="multi",
    )
    log.info("Done.")


def main() -> None:
    if not MODEL_PATH.exists():
        log.error("No trained model at %s. Run train_model.py first.", MODEL_PATH)
        return

    log.info("Loading model from %s", MODEL_PATH)
    model = joblib.load(MODEL_PATH)

    threshold = load_optimal_threshold()
    log.info("Using decision threshold: %.3f", threshold)

    engine = get_engine()
    df = load_recent_flights(engine)
    if df.empty:
        log.warning("flight_features is empty. Nothing to score.")
        return

    scored = predict(df, model, threshold=threshold)
    save_to_postgres(scored, engine)


if __name__ == "__main__":
    main()
