import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from jose import JWTError, jwt
from passlib.context import CryptContext

from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

ROLE_ADMIN = "admin"
ROLE_MANAGER = "business_manager"
ROLE_ANALYST = "analyst"
ALL_ROLES = [ROLE_ADMIN, ROLE_MANAGER, ROLE_ANALYST]


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return pwd_context.verify(plain, hashed)
    except Exception:
        return False


def create_access_token(subject: str, role: str, expires_minutes: int | None = None) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=expires_minutes or settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": subject, "role": role, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
    except JWTError:
        return None


def generate_api_key() -> str:
    return "fk_" + secrets.token_urlsafe(32)


def hash_api_key(api_key: str) -> str:
    return hashlib.sha256((api_key + settings.API_KEY_SALT).encode()).hexdigest()


def sign_payload(payload: bytes, api_key: str) -> str:
    """Optional HMAC request signing for external integrations."""
    return hmac.new(api_key.encode(), payload, hashlib.sha256).hexdigest()
