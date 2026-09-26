from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import select
from sqlalchemy.orm import Session

from .audit import audit
from .config import get_settings
from .db import get_db
from .deps import get_current_user, get_request_context
from .models import User
from .rate_limit import enforce_rate_limit
from .schemas import TokenOut, UserCreate, UserOut
from .security import create_access_token, hash_password, verify_password

router = APIRouter(prefix="/auth", tags=["Auth"])
settings = get_settings()


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: UserCreate, request: Request, db: Session = Depends(get_db)):
    enforce_rate_limit(request, "auth-register", settings.auth_rate_limit_per_minute)
    email = payload.email.lower()
    existing = db.scalar(select(User).where(User.email == email))
    if existing:
        raise HTTPException(status_code=409, detail="An account with this email already exists")
    user = User(email=email, password_hash=hash_password(payload.password))
    db.add(user)
    db.flush()
    audit(db, user=user, action="researcher.register", resource_type="user", resource_id=user.id, context=get_request_context(request))
    db.commit()
    db.refresh(user)
    return user


@router.post("/login", response_model=TokenOut)
def login(request: Request, form: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    enforce_rate_limit(request, "auth-login", settings.auth_rate_limit_per_minute)
    user = db.scalar(select(User).where(User.email == form.username.lower()))
    if not user or not verify_password(form.password, user.password_hash):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Incorrect email or password")
    audit(db, user=user, action="researcher.login", resource_type="user", resource_id=user.id, context=get_request_context(request))
    db.commit()
    return TokenOut(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(get_current_user)):
    return user
