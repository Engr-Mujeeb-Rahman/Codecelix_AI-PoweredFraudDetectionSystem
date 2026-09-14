from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class TransactionBase(BaseModel):
    customer_id: str
    amount: float = Field(gt=0)
    currency: str = "USD"
    payment_method: str = "card"
    ip_address: str | None = None
    device_id: str | None = None
    country: str | None = None
    city: str | None = None
    device_info: str | None = None
    account_age_days: int | None = None
    signup_date: datetime | None = None
    customer_email: str | None = None
    customer_name: str | None = None
    transaction_id: str | None = None  # external id
    created_at: datetime | None = None


class TransactionCreate(TransactionBase):
    pass


class TransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    txn_external_id: str | None
    customer_id: str
    amount: float
    currency: str
    payment_method: str
    status: str
    device_id: str | None
    ip_id: str | None
    ip_address_str: str | None
    country: str | None
    city: str | None
    device_info: str | None
    account_age_days: int | None
    reviewed: bool
    created_at: datetime


class Paginated(BaseModel):
    total: int
    page: int
    page_size: int
    items: list
