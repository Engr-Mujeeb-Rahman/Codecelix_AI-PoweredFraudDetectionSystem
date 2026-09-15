from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.core.deps import get_current_user, require_roles
from app.db.session import get_db
from app.models.api_client import ApiClient
from app.models.risk_assessment import RiskAssessment
from app.models.transaction import Transaction
from app.models.user import User
from app.schemas.risk import (
    MLMetricsOut,
    MLRetrainResponse,
    RiskAssessmentOut,
    RiskCheckRequest,
    RiskCheckResponse,
)
from app.services.decision_engine import evaluate_transaction_risk
from app.services.ml_detector import get_ml_metrics, train_ml_model

router = APIRouter()

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)


def get_client_or_user(
    db: Session = Depends(get_db),
    api_key: str | None = Security(api_key_header),
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
):
    """Allows either X-API-Key (external) or Bearer JWT (internal) access."""
    if api_key:
        client = db.query(ApiClient).filter(ApiClient.key_hash == security.hash_api_key(api_key)).first()
        if client and client.is_active:
            client.requests_count += 1
            db.commit()
            return {"type": "client", "entity": client}

    if credentials:
        payload = security.decode_token(credentials.credentials)
        if payload:
            user = db.query(User).filter(User.id == payload.get("sub")).first()
            if user and user.is_active:
                return {"type": "user", "entity": user}

    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required (X-API-Key or Bearer Token)")


@router.post("/risk-check", response_model=RiskCheckResponse)
def check_risk(
    payload: RiskCheckRequest,
    db: Session = Depends(get_db),
    auth=Depends(get_client_or_user),
):
    """Real-time transaction risk scoring without necessarily persisting a transaction."""
    result = evaluate_transaction_risk(
        db=db,
        amount=payload.amount,
        customer_id=payload.customer_id,
        payment_method=payload.payment_method,
        currency=payload.currency,
        device_id=payload.device_id,
        ip_address=payload.ip_address,
        country=payload.country,
        city=payload.city,
        device_info=payload.device_info,
        created_at=payload.created_at,
        auto_alert=False,
    )
    return RiskCheckResponse(**result)


@router.get("/risk/{transaction_id}", response_model=RiskAssessmentOut)
def get_transaction_risk(
    transaction_id: str,
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Retrieves the stored risk assessment for a specific transaction."""
    assessment = (
        db.query(RiskAssessment)
        .filter(RiskAssessment.transaction_id == transaction_id)
        .first()
    )
    if not assessment:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Risk assessment not found for this transaction")
    return assessment


@router.get("/risk-metrics", response_model=MLMetricsOut)
def ml_metrics(
    db: Session = Depends(get_db),
    user=Depends(get_current_user),
):
    """Retrieves ML anomaly detection model status, precision, and recall metrics."""
    return get_ml_metrics(db)


@router.post("/risk/retrain", response_model=MLRetrainResponse)
def retrain_model(
    db: Session = Depends(get_db),
    user=Depends(require_roles("admin")),
):
    """Admin endpoint to trigger ML Anomaly Detection retraining on transaction history."""
    res = train_ml_model(db)
    return MLRetrainResponse(**res)
