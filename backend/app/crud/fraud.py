"""CRUD for users, customers, transactions, alerts, investigations, feedback."""
from datetime import timedelta, timezone
from uuid import uuid4

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core import security
from app.models.alert import ALERT_STATUSES, Alert
from app.models.customer import Customer
from app.models.investigation import Investigation
from app.models.model_feedback import ModelFeedback
from app.models.report import AuditLog
from app.models.transaction import Transaction
from app.models.user import User
from app.utils.datetime import utcnow


# ---------- Users ----------
def create_user(db: Session, email: str, password: str, full_name: str, role: str) -> User:
    user = User(
        id=str(uuid4()),
        email=email.lower(),
        full_name=full_name,
        hashed_password=security.hash_password(password),
        role=role,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def get_user_by_email(db: Session, email: str) -> User | None:
    return db.query(User).filter(User.email == email.lower()).first()


# ---------- Customers ----------
def update_customer_profile(db: Session, customer_id: str):
    """Recompute plain aggregate counters on the customer profile."""
    c = db.query(Customer).filter(Customer.id == customer_id).first()
    if not c:
        return
    txns = (
        db.query(Transaction)
        .filter(Transaction.customer_id == customer_id)
        .order_by(Transaction.created_at.desc())
        .all()
    )
    c.total_transactions = len(txns)
    c.suspicious_transactions = sum(1 for t in txns if t.status == "blocked")
    c.previous_fraud_reports = sum(
        1 for t in txns
        if db.query(Alert)
        .filter(Alert.transaction_id == t.id, Alert.status == "confirmed_fraud")
        .count()
        > 0
    )
    amounts = [t.amount for t in txns]
    c.avg_amount = sum(amounts) / len(amounts) if amounts else 0.0
    c.min_amount = min(amounts) if amounts else 0.0
    c.max_amount = max(amounts) if amounts else 0.0

    def _aware(dt):
        if dt is None:
            return None
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)

    now = utcnow()
    txn_times = [_aware(t.created_at) for t in txns]
    c.txn_velocity_1h = sum(1 for t in txn_times if t >= now - timedelta(hours=1))
    c.txn_velocity_24h = sum(1 for t in txn_times if t >= now - timedelta(hours=24))
    c.last_txn_at = txn_times[0] if txn_times else None
    db.commit()


# ---------- Alerts ----------
def create_alert_for_txn(db: Session, txn: Transaction, title: str, reason: str | None,
                         severity: str, user_id: str | None = None) -> Alert:
    alert = Alert(
        id=str(uuid4()),
        transaction_id=txn.id,
        customer_id=txn.customer_id,
        title=title,
        reason=reason,
        severity=severity,
        created_by=user_id,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def review_alert(db: Session, alert: Alert, status: str, note: str | None,
                 user) -> Alert:
    """Update alert status; record feedback for confirmed/false-positive decisions."""
    if status not in ALERT_STATUSES:
        raise ValueError(f"status must be one of {ALERT_STATUSES}")
    alert.status = status
    if status in ("confirmed_fraud", "false_positive", "resolved"):
        alert.resolved_at = utcnow()
    if note:
        alert.reason = (alert.reason + " | " + note) if alert.reason else note
    if status in ("confirmed_fraud", "false_positive"):
        db.add(ModelFeedback(
            id=str(uuid4()),
            alert_id=alert.id,
            transaction_id=alert.transaction_id,
            feedback_label=status,
            comment=note,
            created_by=user.id,
        ))
    db.add(AuditLog(
        id=str(uuid4()),
        user_id=user.id,
        user_email=user.email,
        action=f"alert_review:{status}",
        entity_type="alert",
        entity_id=alert.id,
    ))
    db.commit()
    db.refresh(alert)
    return alert


# ---------- Investigations ----------
def create_investigation(db: Session, transaction_id: str, analyst_id: str | None,
                         notes: str | None) -> Investigation:
    txn = db.query(Transaction).filter(Transaction.id == transaction_id).first()
    if not txn:
        raise ValueError("Transaction not found")
    inv = Investigation(
        id=str(uuid4()),
        transaction_id=txn.id,
        customer_id=txn.customer_id,
        analyst_id=analyst_id,
        notes=notes,
    )
    db.add(inv)
    db.commit()
    db.refresh(inv)
    return inv
