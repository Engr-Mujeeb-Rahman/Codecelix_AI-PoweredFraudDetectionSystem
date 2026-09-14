from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class IpAddress(Base):
    __tablename__ = "ip_addresses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    ip: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_vpn_or_proxy: Mapped[bool] = mapped_column(Boolean, default=False)
    customer_count: Mapped[int] = mapped_column(Integer, default=0)
    request_count: Mapped[int] = mapped_column(Integer, default=0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_seen_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    transactions = relationship("Transaction", back_populates="ip_address", lazy="dynamic")


def get_or_create_ip(db, ip: str, country=None, city=None, is_vpn=False) -> "IpAddress":
    row = db.query(IpAddress).filter(IpAddress.ip == ip).first()
    if row:
        if country and not row.country:
            row.country = country
        if city and not row.city:
            row.city = city
        if is_vpn:
            row.is_vpn_or_proxy = True
        return row
    row = IpAddress(id=str(uuid4()), ip=ip, country=country, city=city, is_vpn_or_proxy=is_vpn)
    db.add(row)
    db.flush()
    return row


from uuid import uuid4  # noqa: E402
