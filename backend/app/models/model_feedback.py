from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class ModelFeedback(Base):
    """Analyst feedback on alerts (confirmed fraud / false positive)."""

    __tablename__ = "model_feedback"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    alert_id: Mapped[str | None] = mapped_column(ForeignKey("alerts.id"), index=True, nullable=True)
    transaction_id: Mapped[str | None] = mapped_column(ForeignKey("transactions.id"), index=True, nullable=True)
    feedback_label: Mapped[str] = mapped_column(String(32), index=True, nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    alert = relationship("Alert")
    transaction = relationship("Transaction")
