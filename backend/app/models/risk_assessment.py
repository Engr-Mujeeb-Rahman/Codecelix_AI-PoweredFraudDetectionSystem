from datetime import datetime
from uuid import uuid4

from typing import Any
from sqlalchemy import DateTime, Float, ForeignKey, JSON, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.utils.datetime import utcnow

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class RiskAssessment(Base):
    """Stores the full risk evaluation for a transaction."""

    __tablename__ = "risk_assessments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("transactions.id"), unique=True, index=True, nullable=False
    )
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), index=True, nullable=False
    )

    risk_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), nullable=False, default="LOW")
    decision: Mapped[str] = mapped_column(String(16), nullable=False, default="APPROVE")

    ml_anomaly_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    rule_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    customer_behavior_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    triggered_rules: Mapped[Any | None] = mapped_column(JSON_TYPE, nullable=True)
    detected_patterns: Mapped[Any | None] = mapped_column(JSON_TYPE, nullable=True)
    ai_explanation: Mapped[str] = mapped_column(Text, nullable=False)
    features_snapshot: Mapped[Any | None] = mapped_column(JSON_TYPE, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    transaction = relationship("Transaction")
    customer = relationship("Customer")
