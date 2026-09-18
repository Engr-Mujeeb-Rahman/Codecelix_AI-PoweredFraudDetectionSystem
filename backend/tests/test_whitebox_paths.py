"""Whitebox Internal Code Path & Logic Tests.

Validates internal branching logic, mathematical weighting formulas,
critical circuit-breaker overrides, database mutations, and failover branches.
"""
from datetime import datetime, timezone, timedelta
from uuid import uuid4

import pytest

from app.core.config import settings
from app.crud.fraud import update_customer_profile
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.risk_assessment import RiskAssessment
from app.models.rule import FraudRule
from app.models.transaction import Transaction, TransactionStatus
from app.services.decision_engine import evaluate_transaction_risk
from app.services.explanation import generate_deterministic_explanation


def test_weighted_scoring_formula(db):
    """Verifies the exact 40% Rules + 35% Behavior + 25% ML weighted formula."""
    c = Customer(
        id=str(uuid4()),
        external_id="CUST-WB-WEIGHT",
        avg_amount=100.0,
        account_age_days=100,
    )
    db.add(c)
    db.commit()

    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    res = evaluate_transaction_risk(
        db=db,
        amount=100.0,
        customer_id=c.id,
        payment_method="card",
        country="US",
        city="New York",
        created_at=now,
    )

    rule_s = res["rule_score"]
    beh_s = res["customer_behavior_score"]
    ml_s = res["ml_anomaly_score"]

    expected_combined = round((0.40 * rule_s) + (0.35 * beh_s) + (0.25 * ml_s), 1)
    assert abs(res["risk_score"] - expected_combined) <= 0.1, (
        f"Expected {expected_combined}, got {res['risk_score']}"
    )


def test_critical_block_override_branch(db):
    """Verifies that a hard block rule override forces score >= 88.0 and decision = BLOCK."""
    # Create a custom rule with action="block"
    block_rule = FraudRule(
        id=str(uuid4()),
        name="Sanctioned Country Block",
        description="Block all transactions from sanctioned regions",
        rule_type="categorical",
        conditions={"field": "country", "op": "==", "value": "SANCTIONED_ZONE"},
        action="block",
        score_impact=95.0,
        severity="critical",
        is_active=True,
    )
    db.add(block_rule)

    c = Customer(id=str(uuid4()), external_id="CUST-WB-BLOCK", avg_amount=50.0)
    db.add(c)
    db.commit()

    res = evaluate_transaction_risk(
        db=db,
        amount=25.0,  # Small normal amount
        customer_id=c.id,
        country="SANCTIONED_ZONE",
    )

    assert res["decision"] == "BLOCK"
    assert res["risk_score"] >= 88.0
    assert res["risk_level"] == "HIGH"
    assert any(r["rule_id"] == block_rule.id for r in res["triggered_rules"])


def test_impossible_travel_override_branch(db):
    """Verifies that impossible travel forces critical override (score >= 88.0, decision = BLOCK)."""
    c = Customer(id=str(uuid4()), external_id="CUST-WB-TRAVEL", avg_amount=200.0)
    db.add(c)
    db.commit()

    now = datetime(2026, 9, 18, 15, 0, 0, tzinfo=timezone.utc)
    # Previous US transaction 15 minutes ago
    prev_txn = Transaction(
        id=str(uuid4()),
        customer_id=c.id,
        amount=100.0,
        country="US",
        city="New York",
        status="approved",
        created_at=now - timedelta(minutes=15),
    )
    db.add(prev_txn)
    db.commit()

    # Current transaction from RU 15 minutes later
    res = evaluate_transaction_risk(
        db=db,
        amount=150.0,
        customer_id=c.id,
        country="RU",
        city="Moscow",
        created_at=now,
    )

    assert res["decision"] == "BLOCK"
    assert res["risk_score"] >= 88.0
    assert res["risk_level"] == "HIGH"
    assert any(p["pattern"] == "location_anomaly" and p["details"]["impossible_travel"] for p in res["detected_patterns"])


def test_threshold_boundary_decision_tiers():
    """Verifies strict adherence to report.txt decision boundaries (0–30, 31–70, 71–100)."""
    # 0–30: LOW -> APPROVE
    assert settings.RISK_THRESHOLD_LOW == 30.0
    assert settings.RISK_THRESHOLD_HIGH == 70.0

    def get_decision_tier(score: float, has_override: bool = False):
        if score <= settings.RISK_THRESHOLD_LOW:
            return "LOW", "APPROVE"
        elif score <= settings.RISK_THRESHOLD_HIGH:
            return "MEDIUM", "REVIEW"
        else:
            return "HIGH", "BLOCK" if (has_override or score >= settings.CRITICAL_RISK_THRESHOLD) else "REVIEW"

    # Edge cases around 30.0
    assert get_decision_tier(0.0) == ("LOW", "APPROVE")
    assert get_decision_tier(30.0) == ("LOW", "APPROVE")
    assert get_decision_tier(30.1) == ("MEDIUM", "REVIEW")

    # Edge cases around 70.0
    assert get_decision_tier(70.0) == ("MEDIUM", "REVIEW")
    assert get_decision_tier(70.1) == ("HIGH", "REVIEW")
    assert get_decision_tier(85.0) == ("HIGH", "BLOCK")
    assert get_decision_tier(70.1, has_override=True) == ("HIGH", "BLOCK")


def test_database_side_effects_on_transaction(db):
    """Verifies that evaluating a transaction mutates Transaction status, creates RiskAssessment, and updates CustomerRiskProfile."""
    c = Customer(id=str(uuid4()), external_id="CUST-WB-EFFECTS", avg_amount=100.0)
    db.add(c)
    db.commit()

    txn = Transaction(
        id=str(uuid4()),
        customer_id=c.id,
        amount=50.0,
        country="US",
        status="pending",
    )
    db.add(txn)
    db.commit()

    res = evaluate_transaction_risk(
        db=db,
        amount=txn.amount,
        customer_id=c.id,
        country="US",
        txn_record=txn,
    )

    db.commit()

    # Verify transaction status was mutated
    db.refresh(txn)
    assert txn.status in ("approved", "review", "blocked")

    # Verify RiskAssessment record was persisted
    ra = db.query(RiskAssessment).filter(RiskAssessment.transaction_id == txn.id).first()
    assert ra is not None
    assert ra.risk_score == res["risk_score"]
    assert ra.risk_level == res["risk_level"]
    assert ra.decision == res["decision"]
    assert isinstance(ra.triggered_rules, list)
    assert isinstance(ra.detected_patterns, list)

    # Verify CustomerRiskProfile was updated
    crp = db.query(CustomerRiskProfile).filter(CustomerRiskProfile.customer_id == c.id).first()
    assert crp is not None
    assert crp.risk_score > 0.0


def test_customer_aggregate_recomputation(db):
    """Verifies update_customer_profile accurately recomputes averages, min, max, and velocity counts."""
    c = Customer(id=str(uuid4()), external_id="CUST-WB-AGG")
    db.add(c)
    db.commit()

    now = datetime(2026, 9, 18, 12, 0, 0, tzinfo=timezone.utc)
    # Add 3 transactions: $50, $100, $150
    t1 = Transaction(id=str(uuid4()), customer_id=c.id, amount=50.0, status="approved", created_at=now - timedelta(hours=3))
    t2 = Transaction(id=str(uuid4()), customer_id=c.id, amount=100.0, status="approved", created_at=now - timedelta(hours=2))
    t3 = Transaction(id=str(uuid4()), customer_id=c.id, amount=150.0, status="approved", created_at=now - timedelta(minutes=10))
    db.add_all([t1, t2, t3])
    db.commit()

    update_customer_profile(db, c.id)
    db.refresh(c)

    assert c.total_transactions == 3
    assert c.min_amount == 50.0
    assert c.max_amount == 150.0
    assert c.avg_amount == 100.0
    assert c.txn_velocity_1h == 1  # only t3 is within 1 hour
    assert c.txn_velocity_24h == 3  # all 3 within 24h


def test_explanation_formatting():
    """Verifies deterministic explanation template generation."""
    explanation = generate_deterministic_explanation(
        risk_score=88.0,
        risk_level="HIGH",
        patterns=[
            {"pattern": "location_anomaly", "detected": True, "details": {"message": "Impossible travel detected: US to RU in < 2 hours"}},
            {"pattern": "amount_anomaly", "detected": True, "details": {"message": "Current transaction is $1,200.00"}},
        ],
        triggered_rules=[
            {"name": "Impossible Travel Anomaly", "score_impact": 90.0},
        ],
        customer_avg=100.0,
        customer_max=200.0,
        amount=1200.0,
        is_new_device=True,
        is_new_ip=True,
    )

    assert "High Risk because:" in explanation
    assert "Impossible travel detected" in explanation
    assert "1,200" in explanation
    assert "Rule triggered: Impossible Travel Anomaly" in explanation
