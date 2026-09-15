from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.crud import fraud as crud
from app.crud.base import get_list, get_object, update_object
from app.db.session import get_db
from app.models.alert import ALERT_STATUSES, Alert
from app.models.customer import Customer
from app.models.customer_risk_profile import CustomerRiskProfile
from app.models.investigation import Investigation
from app.models.model_feedback import ModelFeedback
from app.models.report import AuditLog, Report
from app.models.risk_assessment import RiskAssessment
from app.models.transaction import Transaction
from app.schemas.customer import CustomerCreate, CustomerOut, CustomerUpdate
from app.schemas.fraud import (AlertCreate, AlertOut, AlertUpdate, AuditLogOut, InvestigationCreate,
                               InvestigationOut, InvestigationUpdate, ModelFeedbackCreate,
                               ModelFeedbackOut, ReportOut)
from app.schemas.risk import CustomerRiskProfileOut, RiskAssessmentOut
from app.schemas.transaction import TransactionOut
from app.utils.datetime import utcnow

router = APIRouter()


# ---------- Customers ----------
@router.get("/customers", response_model=dict)
def list_customers(db: Session = Depends(get_db), user=Depends(get_current_user),
                   page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                   search: str | None = None):
    result = get_list(db, Customer, page=page, page_size=page_size, search=search,
                      search_fields=("external_id", "email", "full_name"))
    result["items"] = [CustomerOut.model_validate(c).model_dump() for c in result["items"]]
    return result


@router.post("/customers", response_model=CustomerOut, status_code=201)
def create_customer(data: CustomerCreate, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "business_manager"))):
    exists = db.query(Customer).filter(Customer.external_id == data.external_id).first()
    if exists:
        raise HTTPException(409, "Customer external_id already exists")
    c = Customer(id=str(uuid4()), **data.model_dump())
    db.add(c)
    db.commit()
    db.refresh(c)
    return c


@router.get("/customers/{customer_id}", response_model=CustomerOut)
def get_customer(customer_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    c = db.query(Customer).filter((Customer.id == customer_id) |
                                  (Customer.external_id == customer_id)).first()
    if not c:
        raise HTTPException(404, "Customer not found")
    return c


@router.get("/customers/{customer_id}/risk-profile", response_model=CustomerRiskProfileOut)
def get_customer_risk_profile(
    customer_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Retrieves the dynamic AI CustomerRiskProfile row for a customer (404 if not yet scored)."""
    c = db.query(Customer).filter((Customer.id == customer_id) |
                                  (Customer.external_id == customer_id)).first()
    target_id = c.id if c else customer_id
    profile = db.query(CustomerRiskProfile).filter(CustomerRiskProfile.customer_id == target_id).first()
    if not profile:
        raise HTTPException(404, f"No risk profile found for customer '{customer_id}'")
    return profile


@router.patch("/customers/{customer_id}", response_model=CustomerOut)
def update_customer(customer_id: str, data: CustomerUpdate, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "business_manager"))):
    c = get_object(db, Customer, customer_id)
    return update_object(db, c, data.model_dump(exclude_unset=True))


@router.delete("/customers/{customer_id}")
def delete_customer(customer_id: str, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin"))):
    c = get_object(db, Customer, customer_id)
    db.delete(c)
    db.commit()
    return {"deleted": True, "id": customer_id}


# ---------- Alerts ----------
@router.get("/alerts", response_model=dict)
def list_alerts(db: Session = Depends(get_db), user=Depends(get_current_user),
                page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                status: str | None = None, severity: str | None = None,
                customer_id: str | None = None):
    filters = {}
    if status:
        filters["status"] = status
    if severity:
        filters["severity"] = severity
    if customer_id:
        filters["customer_id"] = customer_id
    result = get_list(db, Alert, page=page, page_size=page_size, filters=filters)
    result["items"] = [AlertOut.model_validate(a).model_dump() for a in result["items"]]
    return result


@router.get("/alerts/{alert_id}", response_model=AlertOut)
def get_alert(alert_id: str, db: Session = Depends(get_db), user=Depends(get_current_user)):
    return get_object(db, Alert, alert_id)


@router.post("/alerts", response_model=AlertOut, status_code=201)
def create_alert(data: AlertCreate, db: Session = Depends(get_db),
                 user=Depends(require_roles("admin", "business_manager", "analyst"))):
    txn = get_object(db, Transaction, data.transaction_id)
    alert = crud.create_alert_for_txn(db, txn, data.title, data.reason, data.severity, user.id)
    return alert


@router.post("/alerts/{alert_id}/review", response_model=AlertOut)
def review_alert(alert_id: str, data: dict, db: Session = Depends(get_db),
                 user=Depends(require_roles("admin", "analyst"))):
    """Review an alert: new | investigating | confirmed_fraud | false_positive | resolved."""
    alert = get_object(db, Alert, alert_id)
    try:
        return crud.review_alert(db, alert, data.get("status", ""), data.get("note"), user)
    except ValueError as e:
        raise HTTPException(400, str(e))


# ---------- Investigations ----------
@router.get("/investigations", response_model=list[InvestigationOut])
def list_investigations(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Investigation).order_by(Investigation.created_at.desc()).limit(100).all()


@router.post("/investigations", response_model=InvestigationOut, status_code=201)
def create_investigation(data: InvestigationCreate, db: Session = Depends(get_db),
                         user=Depends(require_roles("admin", "analyst"))):
    try:
        return crud.create_investigation(db, data.transaction_id, user.id, data.notes)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.patch("/investigations/{inv_id}", response_model=InvestigationOut)
def update_investigation(inv_id: str, data: InvestigationUpdate, db: Session = Depends(get_db),
                         user=Depends(require_roles("admin", "analyst"))):
    inv = get_object(db, Investigation, inv_id)
    updates = data.model_dump(exclude_unset=True)
    if updates.get("status") == "closed":
        inv.closed_at = utcnow()
    return update_object(db, inv, updates)


@router.get("/investigations/{inv_id}")
def get_investigation_detail(
    inv_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Full single-transaction investigation detail view linked to AI risk assessment,
    customer history, and related alerts (Requirement 10).
    """
    inv = get_object(db, Investigation, inv_id)

    # Linked RiskAssessment (joined on transaction_id)
    assessment = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.transaction_id == inv.transaction_id)
        .first()
    )
    risk_data = None
    if assessment:
        risk_data = {
            "id": assessment.id,
            "risk_score": assessment.risk_score,
            "risk_level": assessment.risk_level,
            "decision": assessment.decision,
            "ml_anomaly_score": assessment.ml_anomaly_score,
            "rule_score": assessment.rule_score,
            "customer_behavior_score": assessment.customer_behavior_score,
            "triggered_rules": assessment.triggered_rules,
            "detected_patterns": assessment.detected_patterns,
            "ai_explanation": assessment.ai_explanation,
            "created_at": assessment.created_at,
        }

    # Customer recent transaction history (reusing query logic from transactions.py detail view)
    history = (
        db.query(Transaction)
        .filter(Transaction.customer_id == inv.customer_id, Transaction.id != inv.transaction_id)
        .order_by(Transaction.created_at.desc())
        .limit(20)
        .all()
    )

    # Related alerts for the same transaction or customer
    related_alerts = (
        db.query(Alert)
        .filter((Alert.transaction_id == inv.transaction_id) | (Alert.customer_id == inv.customer_id))
        .order_by(Alert.created_at.desc())
        .limit(20)
        .all()
    )

    return {
        "id": inv.id,
        "transaction_id": inv.transaction_id,
        "customer_id": inv.customer_id,
        "analyst_id": inv.analyst_id,
        "status": inv.status,
        "notes": inv.notes,
        "conclusion": inv.conclusion,
        "created_at": inv.created_at,
        "updated_at": inv.updated_at,
        "closed_at": inv.closed_at,
        "risk_assessment": risk_data,
        "customer_history": [TransactionOut.model_validate(t).model_dump() for t in history],
        "related_alerts": [AlertOut.model_validate(a).model_dump() for a in related_alerts],
    }


# ---------- Model feedback ----------
@router.get("/feedback", response_model=list[ModelFeedbackOut])
def list_feedback(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(ModelFeedback).order_by(ModelFeedback.created_at.desc()).limit(200).all()


@router.post("/feedback", response_model=ModelFeedbackOut, status_code=201)
def create_feedback(data: ModelFeedbackCreate, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "analyst"))):
    if data.feedback_label not in ("confirmed_fraud", "false_positive"):
        raise HTTPException(400, "feedback_label must be confirmed_fraud or false_positive")
    fb = ModelFeedback(
        id=str(uuid4()),
        alert_id=data.alert_id,
        transaction_id=data.transaction_id,
        feedback_label=data.feedback_label,
        comment=data.comment,
        created_by=user.id,
    )
    db.add(fb)
    db.commit()
    db.refresh(fb)
    return fb


# ---------- Reports ----------
REPORT_TYPES = ["daily_activity", "monthly_activity", "high_risk_customers",
                "high_risk_transactions", "confirmed_fraud", "false_positives", "fraud_trends"]


def _build_report_payload(db: Session, report_type: str, period_start, period_end) -> dict:
    txn_q = db.query(Transaction)
    if period_start:
        txn_q = txn_q.filter(Transaction.created_at >= period_start)
    if period_end:
        txn_q = txn_q.filter(Transaction.created_at <= period_end)
    txns = txn_q.all()
    by_status = {}
    for t in txns:
        by_status[t.status] = by_status.get(t.status, 0) + 1
    payload = {
        "report_type": report_type,
        "generated_at": utcnow().isoformat(),
        "period": {"start": period_start.isoformat() if period_start else None,
                   "end": period_end.isoformat() if period_end else None},
        "total_transactions": len(txns),
        "status_distribution": by_status,
        "total_amount": round(sum(t.amount for t in txns), 2),
    }
    if report_type == "confirmed_fraud":
        payload["alerts"] = [
            {"id": a.id, "title": a.title, "created_at": str(a.created_at)}
            for a in db.query(Alert).filter(Alert.status == "confirmed_fraud").limit(100).all()
        ]
    elif report_type == "false_positives":
        payload["alerts"] = [
            {"id": a.id, "title": a.title, "created_at": str(a.created_at)}
            for a in db.query(Alert).filter(Alert.status == "false_positive").limit(100).all()
        ]
    return payload


@router.get("/reports", response_model=list[ReportOut])
def list_reports(db: Session = Depends(get_db), user=Depends(get_current_user)):
    return db.query(Report).order_by(Report.created_at.desc()).limit(100).all()


@router.post("/reports", response_model=ReportOut, status_code=201)
def generate_report(data: dict, db: Session = Depends(get_db),
                    user=Depends(require_roles("admin", "business_manager"))):
    report_type = data.get("report_type")
    if report_type not in REPORT_TYPES:
        raise HTTPException(400, f"report_type must be one of {REPORT_TYPES}")
    period_start = data.get("period_start")
    period_end = data.get("period_end")
    payload = _build_report_payload(db, report_type, period_start, period_end)
    report = Report(
        id=str(uuid4()),
        report_type=report_type,
        title=data.get("title", report_type.replace("_", " ").title()),
        period_start=period_start,
        period_end=period_end,
        payload=json.dumps(payload, default=str),
        created_by=user.id,
    )
    db.add(report)
    db.commit()
    db.refresh(report)
    return report


@router.get("/reports/{report_id}/export")
def export_report(report_id: str, format: str = "json",
                  db: Session = Depends(get_db), user=Depends(get_current_user)):
    report = get_object(db, Report, report_id)
    if format == "csv":
        import csv as csv_module
        import io
        payload = json.loads(report.payload or "{}")
        out = io.StringIO()
        writer = csv_module.writer(out)
        writer.writerow(["key", "value"])
        for k, v in payload.items():
            writer.writerow([k, json.dumps(v) if isinstance(v, (dict, list)) else v])
        return {"filename": f"{report.report_type}.csv", "content": out.getvalue()}
    return {"filename": f"{report.report_type}.json", "content": report.payload}


# ---------- Audit logs ----------
@router.get("/audit-logs", response_model=dict)
def list_audit_logs(db: Session = Depends(get_db),
                    user=Depends(require_roles("admin")),
                    page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)):
    result = get_list(db, AuditLog, page=page, page_size=page_size)
    result["items"] = [AuditLogOut.model_validate(a).model_dump() for a in result["items"]]
    return result


import json  # noqa: E402
