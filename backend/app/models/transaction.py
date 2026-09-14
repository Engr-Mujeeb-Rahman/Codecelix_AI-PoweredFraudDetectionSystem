import enum
from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base
from app.models.customer import get_or_create_customer
from app.models.device import get_or_create_device
from app.models.device_usage import get_or_create_device_usage
from app.models.ip_address import get_or_create_ip
from app.utils.datetime import parse_dt, utcnow


class PaymentMethod(str, enum.Enum):
    CARD = "card"
    BANK_TRANSFER = "bank_transfer"
    WALLET = "wallet"
    UPI = "upi"
    CRYPTO = "crypto"
    COD = "cod"
    OTHER = "other"


class TransactionStatus(str, enum.Enum):
    APPROVED = "approved"
    REVIEW = "review"
    BLOCKED = "blocked"


class Transaction(Base):
    __tablename__ = "transactions"
    __table_args__ = (
        Index("ix_txn_customer_created", "customer_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    txn_external_id: Mapped[str | None] = mapped_column(String(64), unique=True, index=True, nullable=True)

    customer_id: Mapped[str] = mapped_column(ForeignKey("customers.id"), index=True, nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    currency: Mapped[str] = mapped_column(String(8), default="USD")
    payment_method: Mapped[str] = mapped_column(String(32), default=PaymentMethod.CARD.value)
    status: Mapped[str] = mapped_column(String(16), default=TransactionStatus.APPROVED.value, index=True)

    device_id: Mapped[str | None] = mapped_column(ForeignKey("devices.id"), index=True, nullable=True)
    ip_id: Mapped[str | None] = mapped_column(ForeignKey("ip_addresses.id"), index=True, nullable=True)
    ip_address_str: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(64), nullable=True)
    city: Mapped[str | None] = mapped_column(String(64), nullable=True)
    device_info: Mapped[str | None] = mapped_column(String(255), nullable=True)

    account_age_days: Mapped[int | None] = mapped_column(Integer, nullable=True)
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    customer = relationship("Customer", back_populates="transactions")
    device = relationship("Device")
    ip_address = relationship("IpAddress", back_populates="transactions")

    def link_device(self, db, fingerprint: str | None, device_type=None, os=None, browser=None):
        if not fingerprint:
            return None
        device = get_or_create_device(db, fingerprint, device_type, os, browser)
        self.device_id = device.id
        self.device_info = self.device_info or f"{device_type or 'unknown'} / {os or 'unknown'}"
        if fingerprint.lower() not in ("unknown", ""):
            get_or_create_device_usage(db, device.id, self.customer_id)
        return device

    def link_ip(self, db, ip: str | None, country=None, city=None, is_vpn=False):
        if not ip:
            return None
        row = get_or_create_ip(db, ip, country, city, is_vpn)
        self.ip_id = row.id
        self.ip_address_str = ip
        self.country = self.country or country
        self.city = self.city or city
        return row


def create_transaction_from_payload(db, payload: dict) -> "Transaction":
    """Normalize an incoming transaction payload (API/CSV/manual) into rows."""
    customer = get_or_create_customer(
        db,
        external_id=str(payload["customer_id"]),
        email=payload.get("customer_email"),
        full_name=payload.get("customer_name"),
        signup_date=parse_dt(payload["signup_date"]) if payload.get("signup_date") else None,
    )

    txn_time = parse_dt(payload["created_at"]) if payload.get("created_at") else utcnow()
    if customer.signup_date:
        signup = customer.signup_date if customer.signup_date.tzinfo else customer.signup_date.replace(tzinfo=timezone.utc)
        account_age_days = max((txn_time - signup).days, 0)
    else:
        account_age_days = payload.get("account_age_days")

    txn = Transaction(
        id=str(uuid4()),
        txn_external_id=payload.get("transaction_id"),
        customer_id=customer.id,
        amount=float(payload["amount"]),
        currency=payload.get("currency", "USD"),
        payment_method=payload.get("payment_method", PaymentMethod.CARD.value),
        created_at=txn_time,
        account_age_days=account_age_days,
        country=payload.get("country"),
        city=payload.get("city"),
        device_info=payload.get("device_info"),
    )
    db.add(txn)
    db.flush()

    if payload.get("device_id"):
        txn.link_device(db, str(payload["device_id"]))
    if payload.get("ip_address"):
        txn.link_ip(db, str(payload["ip_address"]), country=payload.get("country"), city=payload.get("city"))
    return txn
