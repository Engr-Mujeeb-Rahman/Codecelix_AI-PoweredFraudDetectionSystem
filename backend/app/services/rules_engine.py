"""Configurable Rules Engine Service.

Evaluates admin-defined rules against transaction and customer context.
Supports composite condition trees (AND/OR), threshold operators, and rule actions.
"""
import json
import logging
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from app.models.rule import FraudRule, RuleAction, RuleSeverity
from app.utils.datetime import utcnow

logger = logging.getLogger(__name__)


def _compare(actual: Any, op: str, target: Any) -> bool:
    """Safely evaluates a comparison operation."""
    if actual is None:
        return False
    try:
        if op == "==":
            return actual == target
        elif op == "!=":
            return actual != target
        elif op == ">":
            return float(actual) > float(target)
        elif op == ">=":
            return float(actual) >= float(target)
        elif op == "<":
            return float(actual) < float(target)
        elif op == "<=":
            return float(actual) <= float(target)
        elif op == "in":
            return actual in target
        elif op == "contains":
            return str(target).lower() in str(actual).lower()
        return False
    except (ValueError, TypeError):
        return False


def evaluate_condition_tree(conditions: Any, context: dict[str, Any]) -> bool:
    """Evaluates nested JSON condition tree against context."""
    if isinstance(conditions, str):
        try:
            conditions = json.loads(conditions)
        except json.JSONDecodeError:
            return False

    if isinstance(conditions, dict):
        # Check if it's a group: {"operator": "AND"|"OR", "conditions": [...]}
        if "operator" in conditions and "conditions" in conditions:
            op = conditions["operator"].upper()
            sub_conds = conditions["conditions"]
            if op == "OR":
                return any(evaluate_condition_tree(c, context) for c in sub_conds)
            else:  # default AND
                return all(evaluate_condition_tree(c, context) for c in sub_conds)
        # Single condition object: {"field": "amount", "op": ">", "value": 5000}
        if "field" in conditions and "op" in conditions:
            field_name = conditions["field"]
            actual = context.get(field_name)
            return _compare(actual, conditions["op"], conditions.get("value"))

    elif isinstance(conditions, list):
        # Default list of conditions is treated as AND
        return all(evaluate_condition_tree(c, context) for c in conditions)

    return False


def evaluate_rules(
    db: Session,
    context: dict[str, Any],
) -> tuple[float, list[dict[str, Any]], bool, str | None]:
    """Evaluates all active rules against the transaction context.

    Returns:
        (total_rule_score, triggered_rules_list, has_block_override, primary_block_reason)
    """
    active_rules = db.query(FraudRule).filter(FraudRule.is_active == True).all()

    total_score = 0.0
    triggered = []
    has_block = False
    block_reason = None

    for rule in active_rules:
        matched = evaluate_condition_tree(rule.conditions, context)
        if matched:
            total_score += rule.score_impact
            rule_entry = {
                "rule_id": rule.id,
                "name": rule.name,
                "description": rule.description,
                "severity": rule.severity,
                "action": rule.action,
                "score_impact": rule.score_impact,
            }
            triggered.append(rule_entry)

            if rule.action == RuleAction.BLOCK.value or rule.severity == RuleSeverity.CRITICAL.value:
                has_block = True
                block_reason = rule.description or rule.name

    capped_score = min(100.0, total_score)
    return capped_score, triggered, has_block, block_reason


def seed_default_rules(db: Session):
    """Seeds standard fraud rules from the PDF specification if not already present."""
    default_rules = [
        {
            "name": "High Value Transaction Threshold",
            "description": "If transaction amount exceeds $5,000",
            "rule_type": "threshold",
            "conditions": {"field": "amount", "op": ">", "value": 5000},
            "action": RuleAction.INCREASE_RISK.value,
            "score_impact": 40.0,
            "severity": RuleSeverity.HIGH.value,
        },
        {
            "name": "Rapid Velocity Spike",
            "description": "If more than 5 transactions occur in 10 minutes",
            "rule_type": "velocity",
            "conditions": {"field": "rapid_txns_count", "op": ">=", "value": 5},
            "action": RuleAction.FLAG_REVIEW.value,
            "score_impact": 35.0,
            "severity": RuleSeverity.HIGH.value,
        },
        {
            "name": "New Device with High Value",
            "description": "If new device detected and transaction is over $1,000",
            "rule_type": "composite",
            "conditions": {
                "operator": "AND",
                "conditions": [
                    {"field": "is_new_device", "op": "==", "value": True},
                    {"field": "amount", "op": ">", "value": 1000},
                ],
            },
            "action": RuleAction.FLAG_REVIEW.value,
            "score_impact": 45.0,
            "severity": RuleSeverity.HIGH.value,
        },
        {
            "name": "Suspicious IP Sharing",
            "description": "If multiple accounts use the same IP address (>= 3)",
            "rule_type": "network",
            "conditions": {"field": "ip_sharing_count", "op": ">=", "value": 3},
            "action": RuleAction.FLAG_REVIEW.value,
            "score_impact": 30.0,
            "severity": RuleSeverity.MEDIUM.value,
        },
        {
            "name": "New Location Anomaly",
            "description": "If transaction originates from a new country never previously used by customer",
            "rule_type": "location",
            "conditions": {"field": "is_new_country", "op": "==", "value": True},
            "action": RuleAction.FLAG_REVIEW.value,
            "score_impact": 35.0,
            "severity": RuleSeverity.HIGH.value,
        },
        {
            "name": "Impossible Travel Anomaly",
            "description": "If transaction occurs from an impossible geographical location in short time",
            "rule_type": "location",
            "conditions": {"field": "impossible_travel", "op": "==", "value": True},
            "action": RuleAction.BLOCK.value,
            "score_impact": 90.0,
            "severity": RuleSeverity.CRITICAL.value,
        },
    ]

    for r_data in default_rules:
        existing = db.query(FraudRule).filter(FraudRule.name == r_data["name"]).first()
        if not existing:
            db.add(FraudRule(id=str(uuid4()), **r_data))
    db.commit()
