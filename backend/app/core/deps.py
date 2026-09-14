from fastapi import Depends, HTTPException, Security, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, APIKeyHeader
from sqlalchemy.orm import Session

from app.core import security
from app.core.config import settings
from app.db.session import get_db
from app.models.api_client import ApiClient
from app.models.user import User

bearer_scheme = HTTPBearer(auto_error=False)
api_key_header = APIKeyHeader(name=settings.API_KEY_HEADER, auto_error=False)

ROLE_RANK = {security.ROLE_ANALYST: 1, security.ROLE_MANAGER: 2, security.ROLE_ADMIN: 3}


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Security(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    if credentials is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    payload = security.decode_token(credentials.credentials)
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    if not user or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "User not found or inactive")
    return user


def require_roles(*roles: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, f"Requires one of roles: {', '.join(roles)}"
            )
        return user

    return dep


def require_min_role(minimum: str):
    def dep(user: User = Depends(get_current_user)) -> User:
        if ROLE_RANK.get(user.role, 0) < ROLE_RANK[minimum]:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Insufficient role")
        return user

    return dep


def get_api_client(
    api_key: str | None = Security(api_key_header),
    db: Session = Depends(get_db),
) -> ApiClient:
    """Authenticate external integrations via X-API-Key header."""
    if not api_key:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing API key")
    client = db.query(ApiClient).filter(ApiClient.key_hash == security.hash_api_key(api_key)).first()
    if not client or not client.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid API key")
    return client
