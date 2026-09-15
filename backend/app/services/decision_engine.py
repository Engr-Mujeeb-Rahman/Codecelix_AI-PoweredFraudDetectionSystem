"""Risk Decision Engine Service.

Orchestrates the entire real-time fraud pipeline (Requirement 18):
Data Validation -> Rule Engine -> ML/AI Analysis -> Customer History -> Risk Engine -> Risk Score -> Decision -> Alert / Approve / Review
Combines scores, handles rule overrides, updates customer risk profiles, and triggers auto-alerts.
"""
import json
import logging
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.alert import Alert
from app.models.customer import Customer, get_or_create_customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.device_usage import DeviceUsage
from app.models.ip_address import IpAddress
from app.models.risk_assessment import RiskAssessment
from app.models.transaction import Transaction, TransactionStatus
from app.services.explanation import generate_deterministic_explanation
from app.services.ml_detector import compute_ml_anomaly_score
from app.services.patterns import run_all_pattern_checks
from app.services.rules_engine import evaluate_rules
from app.utils.datetime import utcnow

logger = logging.getLogger(__name__)


def _compute_customer_behavior_score(customer: Customer, amount: float, patterns: list[dict[str, Any]]) -> float:
    """Computes customer behavior risk score (0–100)."""
    score = 10.0

    avg = customer.avg_amount or 0.0
    if avg > 0:
        ratio = amount / avg
        if ratio >= 4.0:
            score += 45.0
        elif ratio >= 2.5:
            score += 30.0
        elif ratio >= 1.5:
            score += 15.0
    elif amount >= 1000.0:
        score += 35.0

    # Past suspicious history
    if customer.suspicious_transactions > 0:
        score += min(30.0, customer.suspicious_transactions * 10.0)
    if customer.previous_fraud_reports > 0:
        score += min(40.0, customer.previous_fraud_reports * 20.0)

    # Pattern additions to behavior
    for p in patterns:
        if p.get("detected") and p.get("pattern") in ("behavior_change", "amount_anomaly"):
            score += p.get("score_contribution", 0.0)

    return min(100.0, max(0.0, score))


def evaluate_transaction_risk(
    db: Session,
    amount: float,
    customer_id: str,
    payment_method: str = "card",
    currency: str = "USD",
    device_id: str | None = None,
    ip_address: str | None = None,
    country: str | None = None,
    city: str | None = None,
    device_info: str | None = None,
    created_at: datetime | None = None,
    txn_record: Transaction | None = None,
    auto_alert: bool = True,
) -> dict[str, Any]:
    """Runs the complete real-time scoring pipeline on a transaction.

    Can be invoked both for pre-scoring (/api/risk-check) and on persisted transactions.
    """
    txn_time = created_at or (txn_record.created_at if txn_record else utcnow())

    # 1. Fetch or resolve customer
    customer = (
        db.query(Customer)
        .filter((Customer.id == customer_id) | (Customer.external_id == customer_id))
        .first()
    )
    if not customer:
        customer = get_or_create_customer(db, external_id=customer_id)

    # 2. Check Device & IP novelty
    is_new_device = False
    if device_id:
        from app.models.device import Device
        dev_obj = db.query(Device).filter((Device.id == device_id) | (Device.fingerprint == device_id)).first()
        if dev_obj:
            prev_usage = (
                db.query(DeviceUsage)
                .filter(DeviceUsage.device_id == dev_obj.id, DeviceUsage.customer_id == customer.id)
                .first()
            )
            # If no previous usage or usage_count <= 1 (created just now by link_device)
            is_new_device = (prev_usage is None or prev_usage.usage_count <= 1)
        else:
            is_new_device = True

    exclude_id = txn_record.id if txn_record else None
    is_new_ip = False
    is_vpn = False
    if ip_address:
        prev_ip_query = (
            db.query(Transaction)
            .filter(Transaction.ip_address_str == ip_address, Transaction.customer_id == customer.id)
        )
        if exclude_id:
            prev_ip_query = prev_ip_query.filter(Transaction.id != exclude_id)
        is_new_ip = prev_ip_query.first() is None
        ip_row = db.query(IpAddress).filter(IpAddress.ip == ip_address).first()
        if ip_row:
            is_vpn = ip_row.is_vpn_or_proxy

    # 3. Pattern Detection (6 patterns)
    pattern_results = run_all_pattern_checks(
        db=db,
        customer=customer,
        amount=amount,
        device_id=device_id,
        ip_str=ip_address,
        country=country,
        city=city,
        current_time=txn_time,
        exclude_txn_id=exclude_id,
    )

    rapid_count = 1
    device_sharing_count = 1
    ip_sharing_count = 1
    impossible_travel = False
    is_new_country = False

    for p in pattern_results:
        if p.get("pattern") == "rapid_transactions":
            rapid_count = p.get("details", {}).get("count", 1)
        elif p.get("pattern") == "device_sharing":
            device_sharing_count = p.get("details", {}).get("shared_account_count", 1)
        elif p.get("pattern") == "ip_sharing":
            ip_sharing_count = p.get("details", {}).get("shared_account_count", 1)
        elif p.get("pattern") == "location_anomaly":
            impossible_travel = p.get("details", {}).get("impossible_travel", False)
            if p.get("detected"):
                is_new_country = True

    # 4. Rules Engine Evaluation
    rule_context = {
        "amount": amount,
        "payment_method": payment_method,
        "currency": currency,
        "country": country,
        "city": city,
        "is_new_device": is_new_device,
        "is_new_ip": is_new_ip,
        "is_new_country": is_new_country,
        "is_vpn": is_vpn,
        "account_age_days": customer.account_age_days or 0,
        "rapid_txns_count": rapid_count,
        "device_sharing_count": device_sharing_count,
        "ip_sharing_count": ip_sharing_count,
        "impossible_travel": impossible_travel,
        "total_transactions": customer.total_transactions,
    }
    rule_score, triggered_rules, has_block_override, block_reason = evaluate_rules(db, rule_context)

    # 5. ML Anomaly Score
    ml_anomaly_score, ml_mode = compute_ml_anomaly_score(
        amount=amount,
        customer=customer,
        is_new_device=is_new_device,
        is_new_ip=is_new_ip,
        is_vpn=is_vpn,
        created_at=txn_time,
        rapid_count=rapid_count,
    )

    # 6. Customer Behavior Score
    behavior_score = _compute_customer_behavior_score(customer, amount, pattern_results)

    # 7. Final Risk Score Computation (Weighted Combination per PDF)
    # Weights: Rules 40%, Behavior 35%, ML 25%
    combined_score = (0.40 * rule_score) + (0.35 * behavior_score) + (0.25 * ml_anomaly_score)

    if has_block_override or impossible_travel:
        combined_score = max(combined_score, 88.0)

    final_risk_score = round(max(0.0, min(100.0, combined_score)), 1)

    # 8. Risk Level & Decision
    if final_risk_score <= settings.RISK_THRESHOLD_LOW:
        risk_level = "LOW"
        decision = "APPROVE"
    elif final_risk_score <= settings.RISK_THRESHOLD_HIGH:
        risk_level = "MEDIUM"
        decision = "REVIEW"
    else:
        risk_level = "HIGH"
        decision = "BLOCK" if (has_block_override or final_risk_score >= settings.CRITICAL_RISK_THRESHOLD) else "REVIEW"

    # 9. Explanation Generation
    explanation = generate_deterministic_explanation(
        risk_score=final_risk_score,
        risk_level=risk_level,
        patterns=pattern_results,
        triggered_rules=triggered_rules,
        customer_avg=customer.avg_amount or 0.0,
        customer_max=customer.max_amount or 0.0,
        amount=amount,
        is_new_device=is_new_device,
        is_new_ip=is_new_ip,
    )

    # 10. Persist Assessment & Side Effects if txn_record exists
    assessment = None
    if txn_record:
        # Update transaction status
        if decision == "BLOCK":
            txn_record.status = TransactionStatus.BLOCKED.value
        elif decision == "REVIEW":
            txn_record.status = TransactionStatus.REVIEW.value
        else:
            txn_record.status = TransactionStatus.APPROVED.value

        # Create or update RiskAssessment record
        existing_assessment = (
            db.query(RiskAssessment)
            .filter(RiskAssessment.transaction_id == txn_record.id)
            .first()
        )
        if not existing_assessment:
            assessment = RiskAssessment(
                id=str(uuid4()),
                transaction_id=txn_record.id,
                customer_id=customer.id,
                risk_score=final_risk_score,
                risk_level=risk_level,
                decision=decision,
                ml_anomaly_score=ml_anomaly_score,
                rule_score=rule_score,
                customer_behavior_score=round(behavior_score, 1),
                triggered_rules=triggered_rules,
                detected_patterns=[p for p in pattern_results if p.get("detected")],
                ai_explanation=explanation,
                features_snapshot=rule_context,
                created_at=txn_time,
            )
            db.add(assessment)
        else:
            existing_assessment.risk_score = final_risk_score
            existing_assessment.risk_level = risk_level
            existing_assessment.decision = decision
            existing_assessment.ml_anomaly_score = ml_anomaly_score
            existing_assessment.rule_score = rule_score
            existing_assessment.customer_behavior_score = round(behavior_score, 1)
            existing_assessment.triggered_rules = triggered_rules
            existing_assessment.detected_patterns = [p for p in pattern_results if p.get("detected")]
            existing_assessment.ai_explanation = explanation
            assessment = existing_assessment

        # Trigger auto-alert on high risk or review/block
        if auto_alert and (final_risk_score >= settings.RISK_THRESHOLD_HIGH or decision in ("REVIEW", "BLOCK")):
            existing_alert = (
                db.query(Alert).filter(Alert.transaction_id == txn_record.id).first()
            )
            if not existing_alert:
                severity = "critical" if (decision == "BLOCK" or final_risk_score >= settings.CRITICAL_RISK_THRESHOLD) else ("high" if final_risk_score >= settings.RISK_THRESHOLD_HIGH else "medium")
                alert = Alert(
                    id=str(uuid4()),
                    transaction_id=txn_record.id,
                    customer_id=customer.id,
                    title=f"High Risk Transaction (${amount:,.2f} by {customer.external_id})",
                    reason=explanation,
                    severity=severity,
                    status="new",
                )
                db.add(alert)

        # Update CustomerRiskProfile
        update_customer_risk_profile(db, customer.id, final_risk_score, risk_level, assessment.id if assessment else None)

    return {
        "risk_score": final_risk_score,
        "risk_level": risk_level,
        "decision": decision,
        "ml_anomaly_score": ml_anomaly_score,
        "rule_score": rule_score,
        "customer_behavior_score": round(behavior_score, 1),
        "explanation": explanation,
        "triggered_rules": triggered_rules,
        "detected_patterns": [p for p in pattern_results if p.get("detected")],
        "transaction_id": txn_record.id if txn_record else None,
        "assessment_id": assessment.id if assessment else None,
        "ml_mode": ml_mode,
    }


def update_customer_risk_profile(
    db: Session,
    customer_id: str,
    latest_score: float,
    latest_level: str,
    assessment_id: str | None = None,
):
    """Continuously updates the customer's risk profile (Requirement 11)."""
    profile = (
        db.query(CustomerRiskProfile)
        .filter(CustomerRiskProfile.customer_id == customer_id)
        .first()
    )
    if not profile:
        profile = CustomerRiskProfile(
            id=str(uuid4()),
            customer_id=customer_id,
            risk_score=latest_score,
            risk_level=latest_level,
            last_assessment_id=assessment_id,
        )
        db.add(profile)
    else:
        profile.risk_score = latest_score
        profile.risk_level = latest_level
        if assessment_id:
            profile.last_assessment_id = assessment_id

    # Compute unique devices and locations used
    dev_count = (
        db.query(func.count(DeviceUsage.id))
        .filter(DeviceUsage.customer_id == customer_id)
        .scalar() or 0
    )
    loc_count = (
        db.query(Transaction.country)
        .filter(Transaction.customer_id == customer_id, Transaction.country.isnot(None))
        .distinct()
        .count()
    )

    profile.devices_used_count = dev_count
    profile.locations_used_count = loc_count
    profile.updated_at = utcnow()
