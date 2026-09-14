from datetime import datetime
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DeviceUsage(Base):
    """Association: which customer used which device, when."""

    __tablename__ = "device_usages"
    __table_args__ = (UniqueConstraint("device_id", "customer_id", name="uq_device_customer"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    device_id: Mapped[str] = mapped_column(ForeignKey("devices.id"), index=True, nullable=False)
    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    device = relationship("Device", back_populates="usages")
    customer = relationship("Customer")


def get_or_create_device_usage(db, device_id: str, customer_id: str) -> "DeviceUsage":
    du = (
        db.query(DeviceUsage)
        .filter(DeviceUsage.device_id == device_id, DeviceUsage.customer_id == customer_id)
        .first()
    )
    if du:
        du.usage_count += 1
        return du
    du = DeviceUsage(id=str(uuid4()), device_id=device_id, customer_id=customer_id)
    db.add(du)
    db.flush()
    return du
