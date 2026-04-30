"""
Train and compare classification models that predict whether a flight
will arrive 15+ minutes late.

Models compared:
    - LogisticRegression (baseline)
    - RandomForestClassifier
    - XGBClassifier (if xgboost is installed)

The best model (by ROC AUC) is saved to:
    reports/best_delay_model.joblib

All metrics are saved to:
    reports/model_metrics.json

Usage:
    python src/train_model.py
"""

from __future__ import annotations

import json
import logging
from typing import Dict, Tuple

import joblib
import numpy as np
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from config import METRICS_PATH, MODEL_PATH, REPORTS_DIR
from features import (
    CATEGORICAL_FEATURES,
    NUMERIC_FEATURES,
    TARGET,
    load_features,
)


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)
log = logging.getLogger("train_model")


def build_preprocessor() -> ColumnTransformer:
    """Standardize numerics (with median imputation for optional weather cols) and one-hot encode categoricals."""
    numeric_pipeline = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUMERIC_FEATURES),
            (
                "cat",
                OneHotEncoder(handle_unknown="ignore", min_frequency=50),
                CATEGORICAL_FEATURES,
            ),
        ]
    )


def build_models(
    preprocessor: ColumnTransformer,
    scale_pos_weight: float = 4.0,
) -> Dict[str, Pipeline]:
    """Build a dict of named pipelines to compare.

    class_weight='balanced' (LR, RF) and scale_pos_weight (XGBoost) both
    compensate for the ~80/20 on-time/delayed class imbalance, which caused
    near-zero recall at the default 0.5 threshold.
    """
    models: Dict[str, Pipeline] = {
        "logistic_regression": Pipeline(
            steps=[
                ("preprocess", preprocessor),
                (
                    "model",
                    LogisticRegression(
                        max_iter=1000,
                        solver="lbfgs",
                        class_weight="balanced",
                        n_jobs=-1,
                    ),
                ),
            ]
        ),
        "random_forest": Pipeline(
            steps=[
                ("preprocess", preprocessor),
                (
                    "model",
                    RandomForestClassifier(
                        n_estimators=200,
                        max_depth=15,
                        class_weight="balanced",
                        n_jobs=-1,
                        random_state=42,
                    ),
                ),
            ]
        ),
    }

    try:
        from xgboost import XGBClassifier

        models["xgboost"] = Pipeline(
            steps=[
                ("preprocess", preprocessor),
                (
                    "model",
                    XGBClassifier(
                        n_estimators=400,
                        max_depth=6,
                        learning_rate=0.1,
                        scale_pos_weight=scale_pos_weight,
                        eval_metric="logloss",
                        n_jobs=-1,
                        random_state=42,
                    ),
                ),
            ]
        )
        log.info(
            "xgboost detected, including XGBClassifier (scale_pos_weight=%.2f)",
            scale_pos_weight,
        )
    except (ImportError, OSError) as exc:
        # ImportError -> xgboost not installed.
        # OSError     -> xgboost installed but its C library (e.g. libomp
        #                on macOS) is missing. Either way, skip it cleanly.
        log.warning("xgboost unavailable (%s), skipping XGBClassifier", exc)

    return models


def find_optimal_threshold(y_test, y_proba: np.ndarray, min_recall: float = 0.40) -> float:
    """Return the highest-F1 threshold that still achieves at least min_recall.

    The default 0.5 threshold predicted almost everything as on-time on the
    imbalanced BTS dataset (recall ~2%).  Targeting recall >= 40% gives a
    practically useful operating point while keeping precision reasonable.
    """
    precisions, recalls, thresholds = precision_recall_curve(y_test, y_proba)
    # precisions/recalls have n+1 entries; thresholds has n entries
    f1s = (
        2 * precisions[:-1] * recalls[:-1]
        / (precisions[:-1] + recalls[:-1] + 1e-9)
    )
    mask = recalls[:-1] >= min_recall
    if mask.any():
        best_idx = f1s[mask].argmax()
        return float(thresholds[np.where(mask)[0][best_idx]])
    # Fallback: highest-F1 threshold regardless of recall floor
    return float(thresholds[f1s.argmax()])


def evaluate(model: Pipeline, X_test, y_test, threshold: float = 0.5) -> Dict[str, float]:
    """Compute classification metrics at a given decision threshold."""
    y_proba = model.predict_proba(X_test)[:, 1]
    y_pred = (y_proba >= threshold).astype(int)

    return {
        "accuracy":  float(accuracy_score(y_test, y_pred)),
        "precision": float(precision_score(y_test, y_pred, zero_division=0)),
        "recall":    float(recall_score(y_test, y_pred, zero_division=0)),
        "f1":        float(f1_score(y_test, y_pred, zero_division=0)),
        "roc_auc":   float(roc_auc_score(y_test, y_proba)),
        "threshold": threshold,
    }


def train_and_select(
    df,
) -> Tuple[str, Pipeline, Dict[str, Dict[str, float]]]:
    """Train every model, tune decision thresholds, return best model + metric report."""
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]

    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    neg_count = int((y_train == 0).sum())
    pos_count = int((y_train == 1).sum())
    scale_pos_weight = neg_count / max(pos_count, 1)
    log.info(
        "Class distribution — on-time: %d (%.1f%%)  delayed: %d (%.1f%%)  "
        "scale_pos_weight=%.2f",
        neg_count, 100 * neg_count / len(y_train),
        pos_count, 100 * pos_count / len(y_train),
        scale_pos_weight,
    )

    preprocessor = build_preprocessor()
    models = build_models(preprocessor, scale_pos_weight=scale_pos_weight)

    all_metrics: Dict[str, Dict[str, float]] = {}
    best_name, best_score, best_model = None, -np.inf, None

    for name, pipe in models.items():
        log.info("Training %s ...", name)
        pipe.fit(X_train, y_train)

        y_proba = pipe.predict_proba(X_test)[:, 1]
        threshold = find_optimal_threshold(y_test, y_proba)
        metrics = evaluate(pipe, X_test, y_test, threshold=threshold)
        all_metrics[name] = metrics
        log.info(
            "%s -> ROC AUC=%.4f  recall=%.4f  precision=%.4f  threshold=%.3f",
            name,
            metrics["roc_auc"],
            metrics["recall"],
            metrics["precision"],
            metrics["threshold"],
        )

        if metrics["roc_auc"] > best_score:
            best_name, best_score, best_model = name, metrics["roc_auc"], pipe

    log.info("Best model: %s (ROC AUC = %.4f)", best_name, best_score)
    return best_name, best_model, all_metrics


def save_artifacts(
    best_name: str,
    best_model: Pipeline,
    all_metrics: Dict[str, Dict[str, float]],
) -> None:
    """Persist the winning model and all metrics under reports/."""
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(best_model, MODEL_PATH)
    log.info("Saved model to %s", MODEL_PATH)

    payload = {"best_model": best_name, "metrics": all_metrics}
    METRICS_PATH.write_text(json.dumps(payload, indent=2))
    log.info("Saved metrics to %s", METRICS_PATH)


def main() -> None:
    df = load_features(sample_size=500_000)
    best_name, best_model, all_metrics = train_and_select(df)
    save_artifacts(best_name, best_model, all_metrics)


if __name__ == "__main__":
    main()
