from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="medium", index=True)
    status: Mapped[str] = mapped_column(String(32), default="new", index=True)
    assigned_to: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)

    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transaction = relationship("Transaction")
    customer = relationship("Customer")


ALERT_STATUSES = ["new", "investigating", "confirmed_fraud", "false_positive", "resolved"]
