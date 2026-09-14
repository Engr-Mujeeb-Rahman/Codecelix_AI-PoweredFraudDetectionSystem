from datetime import datetime
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.core import security


# ---------- Auth ----------
class UserCreate(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8)
    full_name: str
    role: str = "analyst"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: str
    role: str
    is_active: bool
    created_at: datetime


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ---------- API clients ----------
class ApiClientCreate(BaseModel):
    name: str
    notes: str | None = None
    monthly_quota: int = 100000


class ApiClientOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    is_active: bool
    monthly_quota: int
    requests_count: int
    notes: str | None
    created_at: datetime


class ApiClientCreated(ApiClientOut):
    api_key: str  # only shown once, at creation


# ---------- Helpers ----------
def new_id() -> str:
    return str(uuid4())


def hash_pw(p: str) -> str:
    return security.hash_password(p)
