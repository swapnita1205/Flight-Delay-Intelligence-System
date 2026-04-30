"""
Load the trained model, print metrics, and save evaluation plots.

Outputs:
    reports/figures/confusion_matrix.png
    reports/figures/feature_importance.png  (if model supports it)

Usage:
    python src/evaluate.py
"""

from __future__ import annotations

import json
import logging

import joblib
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import seaborn as sns
from sklearn.metrics import ConfusionMatrixDisplay, confusion_matrix
from sklearn.model_selection import train_test_split

from config import FIGURES_DIR, METRICS_PATH, MODEL_PATH
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
log = logging.getLogger("evaluate")


def print_metrics() -> None:
    """Pretty-print the metrics JSON from training."""
    if not METRICS_PATH.exists():
        log.warning("No metrics file at %s. Run train_model.py first.", METRICS_PATH)
        return

    payload = json.loads(METRICS_PATH.read_text())
    print(f"\nBest model: {payload.get('best_model')}\n")
    print("Per-model metrics:")
    for name, metrics in payload.get("metrics", {}).items():
        print(f"\n  {name}")
        for metric, value in metrics.items():
            print(f"    {metric:>10}: {value:.4f}")


def plot_confusion_matrix(model, X_test, y_test) -> None:
    """Save a labeled confusion matrix figure."""
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    y_pred = model.predict(X_test)
    cm = confusion_matrix(y_test, y_pred)

    fig, ax = plt.subplots(figsize=(6, 5))
    ConfusionMatrixDisplay(
        confusion_matrix=cm,
        display_labels=["On Time", "Delayed"],
    ).plot(ax=ax, cmap="Blues", colorbar=False)
    ax.set_title("Confusion Matrix - Flight Delay Model")
    plt.tight_layout()

    out_path = FIGURES_DIR / "confusion_matrix.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("Saved %s", out_path)


def plot_feature_importance(model) -> None:
    """Save top-20 feature importances if the underlying model supports it."""
    estimator = model.named_steps.get("model")
    preprocess = model.named_steps.get("preprocess")
    if estimator is None or preprocess is None:
        return
    if not hasattr(estimator, "feature_importances_"):
        log.info("Model does not expose feature_importances_, skipping plot.")
        return

    feature_names = preprocess.get_feature_names_out()
    importances = estimator.feature_importances_

    top = (
        pd.DataFrame({"feature": feature_names, "importance": importances})
        .sort_values("importance", ascending=False)
        .head(20)
    )

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.barplot(data=top, x="importance", y="feature", ax=ax, color="steelblue")
    ax.set_title("Top 20 Feature Importances")
    plt.tight_layout()

    out_path = FIGURES_DIR / "feature_importance.png"
    fig.savefig(out_path, dpi=150)
    plt.close(fig)
    log.info("Saved %s", out_path)


def main() -> None:
    if not MODEL_PATH.exists():
        log.error("No model at %s. Run train_model.py first.", MODEL_PATH)
        return

    print_metrics()

    log.info("Loading model from %s", MODEL_PATH)
    model = joblib.load(MODEL_PATH)

    df = load_features(sample_size=100_000)
    X = df[NUMERIC_FEATURES + CATEGORICAL_FEATURES]
    y = df[TARGET]

    _, X_test, _, y_test = train_test_split(
        X, y, test_size=0.2, random_state=42, stratify=y
    )

    plot_confusion_matrix(model, X_test, y_test)
    plot_feature_importance(model)


if __name__ == "__main__":
    main()
