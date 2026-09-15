from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class RiskCheckRequest(BaseModel):
    customer_id: str
    amount: float = Field(gt=0)
    currency: str = "USD"
    payment_method: str = "card"
    ip_address: str | None = None
    device_id: str | None = None
    country: str | None = None
    city: str | None = None
    device_info: str | None = None
    transaction_id: str | None = None
    created_at: datetime | None = None


class RiskCheckResponse(BaseModel):
    risk_score: float = Field(description="Risk Score between 0 and 100")
    risk_level: str = Field(description="LOW (0-30), MEDIUM (31-70), HIGH (71-100)")
    decision: str = Field(description="APPROVE, REVIEW, or BLOCK")
    ml_anomaly_score: float = Field(description="ML Anomaly component score")
    rule_score: float = Field(description="Rules component score")
    customer_behavior_score: float = Field(description="Customer behavior component score")
    explanation: str = Field(description="Human-readable business explanation")
    triggered_rules: list[dict[str, Any]] = Field(default_factory=list)
    detected_patterns: list[dict[str, Any]] = Field(default_factory=list)
    transaction_id: str | None = None


class RiskAssessmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    transaction_id: str
    customer_id: str
    risk_score: float
    risk_level: str
    decision: str
    ml_anomaly_score: float
    rule_score: float
    customer_behavior_score: float
    triggered_rules: Any | None = None
    detected_patterns: Any | None = None
    features_snapshot: Any | None = None
    ai_explanation: str
    created_at: datetime


class CustomerRiskProfileOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    customer_id: str
    risk_score: float
    risk_level: str
    devices_used_count: int
    locations_used_count: int
    updated_at: datetime


class MLMetricsOut(BaseModel):
    total_feedback_samples: int
    confirmed_fraud_count: int
    false_positive_count: int
    estimated_precision: float
    estimated_recall: float
    model_status: str
    last_trained_at: str | None = None


class MLRetrainResponse(BaseModel):
    success: bool
    samples_used: int
    message: str
    trained_at: datetime
