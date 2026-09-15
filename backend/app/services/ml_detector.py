"""Machine Learning Anomaly Detection Service.

Implements Isolation Forest anomaly detection + statistical baseline for cold start.
Extracts numerical feature vectors from transaction and customer profiles.
Handles model persistence, inference, and retraining.
"""
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sqlalchemy.orm import Session

from app.models.customer import Customer
from app.models.model_feedback import ModelFeedback
from app.models.transaction import Transaction
from app.utils.datetime import utcnow

MODEL_DIR = Path(__file__).resolve().parent.parent / "ml" / "artifacts"
MODEL_PATH = MODEL_DIR / "isolation_forest.joblib"
METADATA_PATH = MODEL_DIR / "model_meta.joblib"

_CACHED_MODEL = None
_CACHED_META = None


def _ensure_dir():
    MODEL_DIR.mkdir(parents=True, exist_ok=True)


def extract_features(
    amount: float,
    customer: Customer,
    is_new_device: bool,
    is_new_ip: bool,
    is_vpn: bool,
    created_at: datetime,
    rapid_count: int = 1,
) -> np.ndarray:
    """Extracts a normalized 10-dimensional numerical feature vector."""
    log_amt = math.log(max(1.0, amount))
    avg_amt = customer.avg_amount or 0.0
    amt_ratio = amount / (avg_amt + 1.0)
    acc_age = float(customer.account_age_days or 0)
    vel_1h = float(customer.txn_velocity_1h or rapid_count)
    vel_24h = float(customer.txn_velocity_24h or rapid_count)

    hour = float(created_at.hour) if created_at else 12.0
    day = float(created_at.weekday()) if created_at else 2.0

    new_dev = 1.0 if is_new_device else 0.0
    new_ip = 1.0 if is_new_ip else 0.0
    vpn = 1.0 if is_vpn else 0.0

    return np.array([
        log_amt,
        amt_ratio,
        acc_age,
        vel_1h,
        vel_24h,
        new_dev,
        new_ip,
        vpn,
        hour,
        day,
    ], dtype=float)


def _statistical_anomaly_score(features: np.ndarray, amount: float, customer: Customer) -> float:
    """Cold-start fallback using statistical deviation when ML model is not yet trained."""
    score = 10.0  # baseline normal score

    avg = customer.avg_amount or 0.0
    max_amt = customer.max_amount or 0.0

    # Amount deviation
    if avg > 0:
        ratio = amount / avg
        if ratio > 3.0:
            score += min(45.0, (ratio - 1.0) * 8.0)
        elif ratio > 1.5:
            score += 15.0
    elif amount > 1000.0:
        score += 35.0

    # Velocity deviation
    vel_1h = features[3]
    if vel_1h >= 5:
        score += 30.0
    elif vel_1h >= 3:
        score += 15.0

    # New device / IP penalty
    if features[5] > 0.5:  # is_new_device
        score += 15.0
    if features[6] > 0.5:  # is_new_ip
        score += 10.0
    if features[7] > 0.5:  # is_vpn
        score += 20.0

    return min(100.0, max(0.0, score))


def get_or_load_model() -> tuple[Any | None, dict[str, Any] | None]:
    """Loads the persisted Isolation Forest model and metadata from disk."""
    global _CACHED_MODEL, _CACHED_META
    if _CACHED_MODEL is not None:
        return _CACHED_MODEL, _CACHED_META

    if MODEL_PATH.exists():
        try:
            _CACHED_MODEL = joblib.load(MODEL_PATH)
            if METADATA_PATH.exists():
                _CACHED_META = joblib.load(METADATA_PATH)
            return _CACHED_MODEL, _CACHED_META
        except Exception:
            return None, None
    return None, None


def compute_ml_anomaly_score(
    amount: float,
    customer: Customer,
    is_new_device: bool,
    is_new_ip: bool,
    is_vpn: bool,
    created_at: datetime,
    rapid_count: int = 1,
) -> tuple[float, str]:
    """Computes the ML anomaly score (0–100).

    Returns:
        (anomaly_score, model_mode) where model_mode is 'isolation_forest' or 'statistical_baseline'
    """
    features = extract_features(
        amount=amount,
        customer=customer,
        is_new_device=is_new_device,
        is_new_ip=is_new_ip,
        is_vpn=is_vpn,
        created_at=created_at,
        rapid_count=rapid_count,
    )

    model, meta = get_or_load_model()

    if model is None:
        score = _statistical_anomaly_score(features, amount, customer)
        return round(score, 1), "statistical_baseline"

    try:
        # Decision function: lower values indicate anomalies (typically in [-0.5, 0.5])
        decision_val = model.decision_function(features.reshape(1, -1))[0]
        # Map decision value [-0.3, 0.2] to [100, 0]
        # Negative means anomaly; positive means inlier
        raw_score = (0.15 - decision_val) * 150.0
        calibrated_score = max(0.0, min(100.0, raw_score))
        return round(calibrated_score, 1), "isolation_forest"
    except Exception:
        score = _statistical_anomaly_score(features, amount, customer)
        return round(score, 1), "statistical_baseline"


def train_ml_model(db: Session, min_samples: int = 10) -> dict[str, Any]:
    """Trains or retrains the Isolation Forest model on transactions in the database."""
    global _CACHED_MODEL, _CACHED_META
    _ensure_dir()

    txns = db.query(Transaction).order_by(Transaction.created_at.desc()).limit(2000).all()
    if len(txns) < min_samples:
        return {
            "success": False,
            "message": f"Insufficient historical transactions to train ({len(txns)} < {min_samples}). Baseline active.",
            "samples_used": len(txns),
            "trained_at": utcnow(),
        }

    feature_matrix = []
    for t in txns:
        c = t.customer
        if not c:
            continue
        vec = extract_features(
            amount=t.amount,
            customer=c,
            is_new_device=False,
            is_new_ip=False,
            is_vpn=False,
            created_at=t.created_at or utcnow(),
        )
        feature_matrix.append(vec)

    if len(feature_matrix) < min_samples:
        return {
            "success": False,
            "message": "Not enough valid transaction profiles to train model.",
            "samples_used": len(feature_matrix),
            "trained_at": utcnow(),
        }

    X = np.array(feature_matrix)

    # Train Isolation Forest
    clf = IsolationForest(
        n_estimators=100,
        contamination=0.08,
        random_state=42,
    )
    clf.fit(X)

    meta = {
        "samples_used": len(feature_matrix),
        "trained_at": utcnow().isoformat(),
        "n_features": X.shape[1],
    }

    joblib.dump(clf, MODEL_PATH)
    joblib.dump(meta, METADATA_PATH)

    _CACHED_MODEL = clf
    _CACHED_META = meta

    return {
        "success": True,
        "message": f"Successfully trained Isolation Forest on {len(feature_matrix)} transactions.",
        "samples_used": len(feature_matrix),
        "trained_at": utcnow(),
    }


def get_ml_metrics(db: Session) -> dict[str, Any]:
    """Calculates model metrics and feedback performance."""
    feedback_rows = db.query(ModelFeedback).all()
    total_feedback = len(feedback_rows)
    confirmed_fraud = sum(1 for fb in feedback_rows if fb.feedback_label == "confirmed_fraud")
    false_positives = sum(1 for fb in feedback_rows if fb.feedback_label == "false_positive")

    precision = round(confirmed_fraud / total_feedback, 3) if total_feedback > 0 else 1.0
    # Recall approximation based on confirmed fraud vs total flagged
    recall = round(confirmed_fraud / max(1, confirmed_fraud + (false_positives // 2)), 3) if total_feedback > 0 else 1.0

    model, meta = get_or_load_model()
    status = "trained (IsolationForest)" if model is not None else "cold_start (Statistical Baseline)"
    last_trained = meta.get("trained_at") if meta else None

    return {
        "total_feedback_samples": total_feedback,
        "confirmed_fraud_count": confirmed_fraud,
        "false_positive_count": false_positives,
        "estimated_precision": precision,
        "estimated_recall": recall,
        "model_status": status,
        "last_trained_at": last_trained,
    }
