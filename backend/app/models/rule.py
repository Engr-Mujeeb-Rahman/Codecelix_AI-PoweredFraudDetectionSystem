import enum
from datetime import datetime
from uuid import uuid4

from typing import Any
from sqlalchemy import Boolean, DateTime, Float, JSON, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base
from app.utils.datetime import utcnow

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class RuleAction(str, enum.Enum):
    INCREASE_RISK = "increase_risk"
    FLAG_REVIEW = "flag_review"
    BLOCK = "block"


class RuleSeverity(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class FraudRule(Base):
    """Admin-configurable fraud rule."""

    __tablename__ = "fraud_rules"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    name: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    rule_type: Mapped[str] = mapped_column(String(64), nullable=False, default="threshold")
    conditions: Mapped[Any] = mapped_column(JSON_TYPE, nullable=False)
    action: Mapped[str] = mapped_column(String(32), default=RuleAction.INCREASE_RISK.value)
    score_impact: Mapped[float] = mapped_column(Float, default=20.0)
    severity: Mapped[str] = mapped_column(String(16), default=RuleSeverity.MEDIUM.value)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
