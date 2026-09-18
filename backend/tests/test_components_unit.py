"""Component-Level Unit Tests.

Validates isolated functions, algorithms, feature extractors, pattern detectors,
AST condition evaluators, and cryptographic security utilities without relying on full HTTP requests.
"""
import math
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import numpy as np
import pytest

from app.core.security import (
    create_access_token,
    decode_token,
    generate_api_key,
    hash_api_key,
    hash_password,
    verify_password,
)
from app.models.customer import Customer
from app.models.device import Device
from app.models.device_usage import DeviceUsage
from app.models.ip_address import IpAddress
from app.models.transaction import Transaction
from app.services.ml_detector import (
    _statistical_anomaly_score,
    compute_ml_anomaly_score,
    extract_features,
    extract_raw_features_dict,
    get_or_load_pipeline,
)
from app.services.patterns import (
    detect_amount_anomaly,
    detect_behavior_change,
    detect_device_sharing,
    detect_ip_sharing,
    detect_location_anomaly,
    detect_rapid_transactions,
)
from app.services.rules_engine import evaluate_condition_tree, evaluate_rules


# ============================================================================
# 1. FEATURE EXTRACTION & ML COMPONENTS
# ============================================================================

def test_feature_extraction_all_43_features():
    """Verifies all 43 raw feature names, types, and mathematical properties."""
    pipeline = get_or_load_pipeline()
    assert pipeline is not None, "Production hybrid pipeline must be loadable"
    raw_cols = pipeline["raw_feature_names"]
    assert len(raw_cols) == 43, f"Expected 43 raw columns, got {len(raw_cols)}"

    customer = Customer(
        id=str(uuid4()),
        external_id="CUST-UNIT-01",
        avg_amount=150.0,
        account_age_days=60,
        txn_velocity_1h=2,
    )
    now = datetime(2026, 9, 18, 14, 30, 0, tzinfo=timezone.utc)

    feat_dict = extract_raw_features_dict(
        amount=150.0,
        customer=customer,
        is_new_device=False,
        is_new_ip=False,
        is_vpn=False,
        country="US",
        city="New York",
        payment_method="credit_card",
        device_type="Desktop / Windows",
        created_at=now,
        rapid_count=1,
    )

    # All 43 expected features must be present
    for col in raw_cols:
        assert col in feat_dict, f"Missing expected feature: {col}"
        assert isinstance(feat_dict[col], (int, float)), f"Feature {col} must be numeric"

    # Mathematical checks
    assert feat_dict["amount"] == 150.0
    assert abs(feat_dict["log_amount"] - math.log(150.0)) < 1e-4
    assert feat_dict["amount_deviation"] == 0.0
    assert feat_dict["account_age_days"] == 60.0
    assert feat_dict["new_account_flag"] == 0.0

    # Cyclical hour property: sin^2 + cos^2 = 1.0
    sin_sq = feat_dict["hour_sin"] ** 2
    cos_sq = feat_dict["hour_cos"] ** 2
    assert abs(sin_sq + cos_sq - 1.0) < 1e-5

    # One-hot encodings
    assert feat_dict["payment_credit_card"] == 1.0
    assert feat_dict["device_type_desktop"] == 1.0
    assert feat_dict["country_United States"] == 1.0
    assert feat_dict["country_Germany"] == 0.0


def test_feature_extraction_edge_cases():
    """Verifies feature extractor handles missing stats, unknown countries, and edge amounts."""
    customer = Customer(id=str(uuid4()), external_id="CUST-NEW", avg_amount=0.0, account_age_days=0)

    feat_dict = extract_raw_features_dict(
        amount=0.0,
        customer=customer,
        is_new_device=True,
        country="UNKNOWN_STATE",
        payment_method="crypto_transfer",
        device_type="smart_tv",
    )

    assert feat_dict["amount"] == 0.0
    assert feat_dict["log_amount"] == 0.0  # max(1.0, 0.0) -> log(1.0) = 0.0
    assert feat_dict["new_account_flag"] == 1.0
    assert feat_dict["is_new_device"] == 1.0
    # Foreign/unlisted countries should leave all 10 standard country flags at 0.0
    country_flags = [feat_dict[k] for k in feat_dict if k.startswith("country_")]
    assert sum(country_flags) == 0.0


def test_legacy_10d_feature_extraction():
    """Verifies backward-compatible 10D feature vector."""
    c = Customer(id=str(uuid4()), external_id="CUST-LEGACY", avg_amount=100.0, account_age_days=20)
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    vec = extract_features(100.0, c, is_new_device=False, is_new_ip=False, is_vpn=False, created_at=now)
    assert isinstance(vec, np.ndarray)
    assert vec.shape == (10,)
    assert vec.dtype == float


def test_ml_hybrid_inference_accuracy():
    """Verifies the production hybrid XGBoost + Isolation Forest model scores accurately."""
    c = Customer(id=str(uuid4()), external_id="CUST-LEGIT", avg_amount=80.0, account_age_days=150)
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

    # Legitimate normal transaction
    score_normal, mode = compute_ml_anomaly_score(
        amount=80.0,
        customer=c,
        is_new_device=False,
        is_new_ip=False,
        is_vpn=False,
        created_at=now,
        country="US",
        city="New York",
        payment_method="card",
        device_type="mobile",
        rapid_count=1,
    )
    assert mode == "hybrid_xgb_isolation_forest"
    assert score_normal <= 30.0, f"Expected normal transaction score <= 30.0, got {score_normal}"

    # Fraudulent multi-anomaly transaction (high amount, extreme velocity, new location, new device)
    score_fraud, mode = compute_ml_anomaly_score(
        amount=8500.0,
        customer=c,
        is_new_device=True,
        is_new_ip=True,
        is_vpn=True,
        created_at=now,
        country="RU",
        city="Moscow",
        payment_method="card",
        device_type="mobile",
        rapid_count=6,
        distance_km=7500.0,
        is_new_location=True,
    )
    assert mode == "hybrid_xgb_isolation_forest"
    assert score_fraud >= 70.0, f"Expected fraud transaction score >= 70.0, got {score_fraud}"


def test_statistical_baseline_fallback():
    """Verifies cold-start statistical baseline calculation and boundary limits."""
    c = Customer(id=str(uuid4()), external_id="CUST-FALLBACK", avg_amount=50.0)

    # Baseline normal
    score_normal = _statistical_anomaly_score(50.0, c, False, False, False, 1)
    assert 0.0 <= score_normal <= 30.0

    # Multi-factor penalty
    score_penalty = _statistical_anomaly_score(5000.0, c, True, True, True, 5)
    assert score_penalty >= 70.0
    assert score_penalty <= 100.0


# ============================================================================
# 2. PATTERN DETECTION ENGINES
# ============================================================================

def test_pattern_rapid_transactions(db):
    """Verifies detect_rapid_transactions threshold logic."""
    c = Customer(id=str(uuid4()), external_id="CUST-PAT-01")
    db.add(c)
    db.commit()

    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)

    # 1 previous transaction: below threshold (3)
    t1 = Transaction(id=str(uuid4()), customer_id=c.id, amount=50.0, status="approved", created_at=now - timedelta(minutes=2))
    db.add(t1)
    db.commit()

    res = detect_rapid_transactions(db, c.id, now)
    assert res["detected"] is False

    # Add 2 more within 5 minutes -> total 3 previous -> triggers pattern
    t2 = Transaction(id=str(uuid4()), customer_id=c.id, amount=50.0, status="approved", created_at=now - timedelta(minutes=1))
    t3 = Transaction(id=str(uuid4()), customer_id=c.id, amount=50.0, status="approved", created_at=now - timedelta(seconds=30))
    db.add_all([t2, t3])
    db.commit()

    res = detect_rapid_transactions(db, c.id, now)
    assert res["detected"] is True
    assert res["score_contribution"] == 25.0
    assert res["details"]["count"] >= 3


def test_pattern_device_and_ip_sharing(db):
    """Verifies multi-account device and IP clustering detection."""
    c1 = Customer(id=str(uuid4()), external_id="CUST-DEV-1")
    c2 = Customer(id=str(uuid4()), external_id="CUST-DEV-2")
    db.add_all([c1, c2])
    db.commit()

    dev = Device(id=str(uuid4()), fingerprint="fingerprint-shared-999")
    db.add(dev)
    db.commit()

    # Link device to both customers
    db.add_all([
        DeviceUsage(id=str(uuid4()), device_id=dev.id, customer_id=c1.id, usage_count=1),
        DeviceUsage(id=str(uuid4()), device_id=dev.id, customer_id=c2.id, usage_count=1),
    ])
    db.commit()

    res_dev = detect_device_sharing(db, dev.id, c1.id)
    assert res_dev["detected"] is True
    assert res_dev["score_contribution"] == 30.0

    # IP sharing with 2 distinct accounts
    ip_str = "198.51.100.55"
    db.add_all([
        Transaction(id=str(uuid4()), customer_id=c1.id, amount=20.0, ip_address_str=ip_str, status="approved"),
        Transaction(id=str(uuid4()), customer_id=c2.id, amount=30.0, ip_address_str=ip_str, status="approved"),
    ])
    db.commit()

    res_ip = detect_ip_sharing(db, ip_str, c1.id, threshold=2)
    assert res_ip["detected"] is True
    assert res_ip["score_contribution"] == 25.0


def test_pattern_location_and_impossible_travel(db):
    """Verifies new country detection and impossible travel within 2 hours."""
    c = Customer(id=str(uuid4()), external_id="CUST-TRAVEL-01")
    db.add(c)
    db.commit()

    now = datetime(2026, 9, 18, 14, 0, 0, tzinfo=timezone.utc)
    # Past transaction in US 30 minutes ago
    past_txn = Transaction(
        id=str(uuid4()),
        customer_id=c.id,
        amount=100.0,
        country="US",
        city="New York",
        status="approved",
        created_at=now - timedelta(minutes=30),
    )
    db.add(past_txn)
    db.commit()

    # Same country: consistent
    res_same = detect_location_anomaly(db, c, "US", "New York", now)
    assert res_same["detected"] is False

    # Different country 30 minutes later: impossible travel!
    res_travel = detect_location_anomaly(db, c, "RU", "Moscow", now)
    assert res_travel["detected"] is True
    assert res_travel["details"]["impossible_travel"] is True
    assert res_travel["score_contribution"] == 35.0


def test_pattern_amount_and_behavior_changes(db):
    """Verifies amount deviation and velocity spike detection."""
    c = Customer(
        id=str(uuid4()),
        external_id="CUST-BEHAVE-01",
        avg_amount=100.0,
        max_amount=200.0,
        txn_velocity_1h=4,
        txn_velocity_24h=4,
    )
    db.add(c)
    db.commit()

    # Amount anomaly: $1,200 vs $100 avg (12x)
    res_amt = detect_amount_anomaly(c, 1200.0)
    assert res_amt["detected"] is True
    assert res_amt["score_contribution"] > 0.0

    # Behavior change: velocity spike
    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    res_beh = detect_behavior_change(c, 100.0, now)
    assert res_beh["detected"] is True
    assert res_beh["details"]["velocity_spike"] is True


# ============================================================================
# 3. RULES ENGINE AST CONDITION EVALUATION
# ============================================================================

def test_rules_engine_ast_operators():
    """Verifies AST evaluation across comparison, membership, and containment operators."""
    context = {
        "amount": 1500.0,
        "country": "RU",
        "payment_method": "crypto",
        "is_vpn": True,
        "risk_tier": "VIP",
    }

    # Equality
    assert evaluate_condition_tree({"field": "country", "op": "==", "value": "RU"}, context) is True
    assert evaluate_condition_tree({"field": "country", "op": "==", "value": "US"}, context) is False

    # Inequality
    assert evaluate_condition_tree({"field": "country", "op": "!=", "value": "US"}, context) is True

    # Numeric comparisons
    assert evaluate_condition_tree({"field": "amount", "op": ">", "value": 1000.0}, context) is True
    assert evaluate_condition_tree({"field": "amount", "op": "<", "value": 500.0}, context) is False
    assert evaluate_condition_tree({"field": "amount", "op": ">=", "value": 1500.0}, context) is True
    assert evaluate_condition_tree({"field": "amount", "op": "<=", "value": 1500.0}, context) is True

    # Membership
    assert evaluate_condition_tree({"field": "country", "op": "in", "value": ["RU", "CN", "IR"]}, context) is True
    assert evaluate_condition_tree({"field": "country", "op": "not_in", "value": ["US", "CA", "GB"]}, context) is True

    # Containment
    assert evaluate_condition_tree({"field": "payment_method", "op": "contains", "value": "crypt"}, context) is True

    # Composite Boolean AND / OR
    composite_and = {
        "operator": "AND",
        "conditions": [
            {"field": "amount", "op": ">", "value": 1000.0},
            {"field": "country", "op": "==", "value": "RU"},
        ],
    }
    assert evaluate_condition_tree(composite_and, context) is True

    composite_or = {
        "operator": "OR",
        "conditions": [
            {"field": "amount", "op": ">", "value": 10000.0},  # False
            {"field": "is_vpn", "op": "==", "value": True},      # True
        ],
    }
    assert evaluate_condition_tree(composite_or, context) is True


# ============================================================================
# 4. CRYPTOGRAPHY & SECURITY
# ============================================================================

def test_security_password_hashing():
    """Verifies bcrypt password hashing and constant-time verification."""
    password = "Secur3P@ssw0rd!"
    hashed = hash_password(password)
    assert hashed != password
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(password, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_security_jwt_token_lifecycle():
    """Verifies JWT token encoding, decoding, and expiration rejection."""
    token = create_access_token(subject="user-uuid-123", role="admin", expires_minutes=15)
    assert isinstance(token, str)

    decoded = decode_token(token)
    assert decoded is not None
    assert decoded["sub"] == "user-uuid-123"
    assert decoded["role"] == "admin"

    # Expired token
    expired_token = create_access_token(subject="user-uuid-123", role="admin", expires_minutes=-1)
    assert decode_token(expired_token) is None

    # Tampered token
    tampered = token[:-5] + "XXXXX"
    assert decode_token(tampered) is None


def test_security_api_key_generation_and_hashing():
    """Verifies API key formatting and salted SHA-256 hashing."""
    raw_key = generate_api_key()
    assert raw_key.startswith("fk_")
    assert len(raw_key) > 30

    h1 = hash_api_key(raw_key)
    h2 = hash_api_key(raw_key)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256 hex length
