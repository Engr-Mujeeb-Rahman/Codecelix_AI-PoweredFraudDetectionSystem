from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.utils.datetime import utcnow


class CustomerRiskProfile(Base):
    """Dynamic risk profile for a customer (requirement 11)."""

    __tablename__ = "customer_risk_profiles"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    customer_id: Mapped[str] = mapped_column(
        ForeignKey("customers.id"), unique=True, index=True, nullable=False
    )

    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_level: Mapped[str] = mapped_column(String(16), default="LOW")
    devices_used_count: Mapped[int] = mapped_column(Integer, default=0)
    locations_used_count: Mapped[int] = mapped_column(Integer, default=0)
    last_assessment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )

    customer = relationship("Customer")
