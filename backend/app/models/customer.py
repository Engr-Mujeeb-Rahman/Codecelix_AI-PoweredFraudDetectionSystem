from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Customer(Base):
    __tablename__ = "customers"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    external_id: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    email: Mapped[str | None] = mapped_column(String(255), index=True, nullable=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)

    total_transactions: Mapped[int] = mapped_column(Integer, default=0)
    suspicious_transactions: Mapped[int] = mapped_column(Integer, default=0)
    previous_fraud_reports: Mapped[int] = mapped_column(Integer, default=0)

    # Behavioral aggregates
    avg_amount: Mapped[float] = mapped_column(Float, default=0.0)
    min_amount: Mapped[float] = mapped_column(Float, default=0.0)
    max_amount: Mapped[float] = mapped_column(Float, default=0.0)
    txn_velocity_1h: Mapped[int] = mapped_column(Integer, default=0)
    txn_velocity_24h: Mapped[int] = mapped_column(Integer, default=0)
    last_txn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    account_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    signup_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    transactions = relationship("Transaction", back_populates="customer", lazy="dynamic")


def get_or_create_customer(db, external_id: str, email: str | None = None,
                           full_name: str | None = None, signup_date=None) -> "Customer":
    from app.utils.datetime import utcnow

    c = db.query(Customer).filter(Customer.external_id == external_id).first()
    if c:
        if email and not c.email:
            c.email = email
        if full_name and not c.full_name:
            c.full_name = full_name
        return c
    c = Customer(
        id=str(uuid4()),
        external_id=external_id,
        email=email,
        full_name=full_name,
        signup_date=signup_date,
        account_age_days=(utcnow() - signup_date).days if signup_date else None,
    )
    db.add(c)
    db.flush()
    return c
