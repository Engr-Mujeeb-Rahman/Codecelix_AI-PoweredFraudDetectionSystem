from datetime import datetime

from pydantic import BaseModel, ConfigDict


class CustomerBase(BaseModel):
    external_id: str
    email: str | None = None
    full_name: str | None = None
    signup_date: datetime | None = None
    notes: str | None = None


class CustomerCreate(CustomerBase):
    pass


class CustomerUpdate(BaseModel):
    email: str | None = None
    full_name: str | None = None
    signup_date: datetime | None = None
    notes: str | None = None


class CustomerOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    external_id: str
    email: str | None
    full_name: str | None
    total_transactions: int
    suspicious_transactions: int
    previous_fraud_reports: int
    avg_amount: float
    min_amount: float
    max_amount: float
    txn_velocity_1h: int
    txn_velocity_24h: int
    account_age_days: int | None
    signup_date: datetime | None
    notes: str | None
    created_at: datetime
    updated_at: datetime


class Paginated(BaseModel):
    total: int
    page: int
    page_size: int
    items: list
