import json
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.crud.base import get_list, get_object, update_object
from app.db.session import get_db
from app.models.rule import FraudRule
from app.schemas.rule import RuleCreate, RuleOut, RuleUpdate

router = APIRouter()


@router.get("", response_model=list[RuleOut])
def list_rules(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
    active_only: bool = False,
):
    """Lists all configurable fraud rules."""
    q = db.query(FraudRule)
    if active_only:
        q = q.filter(FraudRule.is_active == True)
    return q.order_by(FraudRule.created_at.desc()).all()


@router.post("", response_model=RuleOut, status_code=201)
def create_rule(
    data: RuleCreate,
    db: Session = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    """Creates a new fraud rule (Admin only)."""
    exists = db.query(FraudRule).filter(FraudRule.name == data.name).first()
    if exists:
        raise HTTPException(status.HTTP_409_CONFLICT, f"Rule with name '{data.name}' already exists")

    conds = data.conditions
    if isinstance(conds, str):
        try:
            conds = json.loads(conds)
        except Exception:
            pass

    rule = FraudRule(
        id=str(uuid4()),
        name=data.name,
        description=data.description,
        rule_type=data.rule_type,
        conditions=conds,
        action=data.action,
        score_impact=data.score_impact,
        severity=data.severity,
        is_active=data.is_active,
        created_by=user.id,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("/{rule_id}", response_model=RuleOut)
def get_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Gets details for a specific fraud rule."""
    return get_object(db, FraudRule, rule_id)


@router.patch("/{rule_id}", response_model=RuleOut)
def update_rule(
    rule_id: str,
    data: RuleUpdate,
    db: Session = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    """Updates an existing fraud rule (Admin only)."""
    rule = get_object(db, FraudRule, rule_id)
    updates = data.model_dump(exclude_unset=True)
    if "conditions" in updates and isinstance(updates["conditions"], str):
        try:
            updates["conditions"] = json.loads(updates["conditions"])
        except Exception:
            pass

    return update_object(db, rule, updates)


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: str,
    db: Session = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    """Deletes a fraud rule (Admin only)."""
    rule = get_object(db, FraudRule, rule_id)
    db.delete(rule)
    db.commit()
    return {"deleted": True, "id": rule_id}
