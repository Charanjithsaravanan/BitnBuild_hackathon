from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError
from sqlalchemy.orm import Session

from .db import get_db
from .models import ParticipantSession, User, hash_participant_token
from .security import decode_access_token

bearer = HTTPBearer(auto_error=False)
participant_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    db: Session = Depends(get_db),
) -> User:
    if not credentials:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    try:
        payload = decode_access_token(credentials.credentials)
        user_id = payload.get("sub")
        if not user_id or payload.get("type") != "access":
            raise ValueError
    except (InvalidTokenError, ValueError):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")

    user = db.get(User, user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


def get_participant_session(
    credentials: HTTPAuthorizationCredentials | None = Depends(participant_bearer),
    db: Session = Depends(get_db),
) -> ParticipantSession:
    if not credentials:
        raise HTTPException(status_code=401, detail="Participant session token required")
    token_hash = hash_participant_token(credentials.credentials)
    session = db.query(ParticipantSession).filter(ParticipantSession.participant_token_hash == token_hash).first()
    if not session:
        raise HTTPException(status_code=401, detail="Invalid participant session token")
    expires_at = session.participant_token_expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if expires_at < datetime.now(timezone.utc):
        raise HTTPException(status_code=401, detail="Participant session token expired")
    return session


def get_request_context(request: Request) -> dict:
    return {
        "ip_address": request.client.host if request.client else None,
        "user_agent": request.headers.get("user-agent", "")[:1000],
    }
