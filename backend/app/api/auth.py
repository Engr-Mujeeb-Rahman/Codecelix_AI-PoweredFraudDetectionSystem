from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_user, require_roles
from app.core import security
from app.crud import fraud as crud
from app.crud.base import get_list, get_object, update_object
from app.db.session import get_db
from app.models.api_client import ApiClient
from app.models.report import AuditLog
from app.models.user import User
from app.schemas.auth import ApiClientCreate, ApiClientCreated, ApiClientOut, Token, UserCreate, UserLogin, UserOut
from app.utils.datetime import utcnow

router = APIRouter()


@router.post("/register", response_model=UserOut, status_code=201)
def register(data: UserCreate, db: Session = Depends(get_db)):
    if data.role not in security.ALL_ROLES:
        raise HTTPException(400, f"role must be one of {security.ALL_ROLES}")
    if crud.get_user_by_email(db, data.email):
        raise HTTPException(409, "Email already registered")
    return crud.create_user(db, data.email, data.password, data.full_name, data.role)


@router.post("/login", response_model=Token)
def login(data: UserLogin, db: Session =Depends(get_db)):
    user = crud.get_user_by_email(db, data.email)
    if not user or not security.verify_password(data.password, user.hashed_password):
        raise HTTPException(401, "Invalid email or password")
    token = security.create_access_token(user.id, user.role)
    user.last_login_at = utcnow()
    db.commit()
    return Token(access_token=token, user=UserOut.model_validate(user))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user


@router.get("/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return db.query(User).all()


@router.patch("/users/{user_id}", response_model=UserOut)
def update_user(user_id: str, data: dict, db: Session = Depends(get_db),
                user: User = Depends(require_roles("admin"))):
    db_user = get_object(db, User, user_id)
    return update_object(db, db_user, data)


@router.post("/api-clients", response_model=ApiClientCreated, status_code=201)
def create_api_client(data: ApiClientCreate, db: Session = Depends(get_db),
                      user: User = Depends(require_roles("admin"))):
    raw_key = security.generate_api_key()
    client = ApiClient(
        id=str(__import__("uuid").uuid4()),
        name=data.name,
        key_hash=security.hash_api_key(raw_key),
        notes=data.notes,
        monthly_quota=data.monthly_quota,
    )
    db.add(client)
    db.commit()
    db.refresh(client)
    out = ApiClientOut.model_validate(client).model_dump()
    return ApiClientCreated(**out, api_key=raw_key)


@router.get("/api-clients", response_model=list[ApiClientOut])
def list_api_clients(db: Session = Depends(get_db), user: User = Depends(require_roles("admin"))):
    return db.query(ApiClient).all()


@router.post("/audit-logs/test")
def write_audit_log_placeholder(user: User = Depends(get_current_user)):
    return {"ok": True}
