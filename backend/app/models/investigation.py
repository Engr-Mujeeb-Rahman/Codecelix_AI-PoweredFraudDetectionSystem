from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Investigation(Base):
    __tablename__ = "investigations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    transaction_id: Mapped[str] = mapped_column(ForeignKey("transactions.id"), index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    analyst_id: Mapped[str | None] = mapped_column(String(36), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="open", index=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    closed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transaction = relationship("Transaction")
    customer = relationship("Customer")
