from datetime import datetime

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    device_type: Mapped[str | None] = mapped_column(String(32), nullable=True)  # mobile/desktop/tablet
    os: Mapped[str | None] = mapped_column(String(64), nullable=True)
    browser: Mapped[str | None] = mapped_column(String(64), nullable=True)
    customer_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    usages = relationship("DeviceUsage", back_populates="device", lazy="dynamic")


def get_or_create_device(db, fingerprint: str, device_type=None, os=None, browser=None) -> "Device":
    d = db.query(Device).filter(Device.fingerprint == fingerprint).first()
    if d:
        for attr, val in (("device_type", device_type), ("os", os), ("browser", browser)):
            if val and not getattr(d, attr):
                setattr(d, attr, val)
        return d
    d = Device(id=str(uuid4()), fingerprint=fingerprint, device_type=device_type, os=os, browser=browser)
    db.add(d)
    db.flush()
    return d


from uuid import uuid4  # noqa: E402
