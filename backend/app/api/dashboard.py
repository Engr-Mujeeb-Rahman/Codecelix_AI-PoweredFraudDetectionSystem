from datetime import timedelta

from fastapi import APIRouter, Depends
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_current_user
from app.db.session import get_db
from app.models.alert import Alert
from app.models.customer import Customer
from app.models.transaction import Transaction
from app.utils.datetime import utcnow

router = APIRouter()


@router.get("")
def dashboard(db: Session = Depends(get_db), user=Depends(get_current_user)):
    now = utcnow()
    week_ago = now - timedelta(days=7)

    total = db.query(func.count(Transaction.id)).scalar() or 0
    blocked = db.query(func.count(Transaction.id)).filter(Transaction.status == "blocked").scalar() or 0
    review = db.query(func.count(Transaction.id)).filter(Transaction.status == "review").scalar() or 0
    approved = db.query(func.count(Transaction.id)).filter(Transaction.status == "approved").scalar() or 0

    alerts_new = db.query(func.count(Alert.id)).filter(Alert.status == "new").scalar() or 0
    confirmed = db.query(func.count(Alert.id)).filter(Alert.status == "confirmed_fraud").scalar() or 0
    false_pos = db.query(func.count(Alert.id)).filter(Alert.status == "false_positive").scalar() or 0

    last7 = (
        db.query(func.date(Transaction.created_at), func.count(Transaction.id))
        .filter(Transaction.created_at >= week_ago)
        .group_by(func.date(Transaction.created_at))
        .all()
    )

    customers = (
        db.query(Customer).order_by(Customer.total_transactions.desc()).limit(10).all()
    )

    from app.models.risk_assessment import RiskAssessment
    from app.models.device_usage import DeviceUsage

    avg_score = db.query(func.avg(RiskAssessment.risk_score)).scalar() or 0.0
    high_risk = db.query(func.count(RiskAssessment.id)).filter(RiskAssessment.risk_level == "HIGH").scalar() or 0
    med_risk = db.query(func.count(RiskAssessment.id)).filter(RiskAssessment.risk_level == "MEDIUM").scalar() or 0
    low_risk = db.query(func.count(RiskAssessment.id)).filter(RiskAssessment.risk_level == "LOW").scalar() or 0

    suspicious_devices = (
        db.query(DeviceUsage.device_id)
        .group_by(DeviceUsage.device_id)
        .having(func.count(DeviceUsage.customer_id) > 1)
        .count()
    )

    return {
        "transactions": {"total": total, "approved": approved, "review": review, "blocked": blocked},
        "alerts": {"new": alerts_new, "confirmed_fraud": confirmed, "false_positive": false_pos},
        "risk_summary": {
            "average_risk_score": round(float(avg_score), 1),
            "high_risk_count": high_risk,
            "medium_risk_count": med_risk,
            "low_risk_count": low_risk,
            "suspicious_devices_count": suspicious_devices,
        },
        "activity_7d": [
            {"date": str(d), "transactions": c} for d, c in last7
        ],
        "top_customers": [
            {"external_id": c.external_id, "total_transactions": c.total_transactions,
             "suspicious_transactions": c.suspicious_transactions}
            for c in customers
        ],
    }

