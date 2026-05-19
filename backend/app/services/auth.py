import uuid
from datetime import datetime, UTC

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.redis import redis_client
from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    verify_password,
)
from app.models.user import User
from app.schemas.auth import LoginRequest, RegisterRequest, TokenResponse

bearer_scheme = HTTPBearer()


async def blacklist_token(token: str) -> None:
    """토큰의 만료 시간(exp)을 구하여, 남은 시간만큼 Redis DB 0에 블랙리스트 키로 보존합니다."""
    try:
        payload = decode_token(token)
        exp = payload.get("exp")
        if exp:
            now = int(datetime.now(UTC).timestamp())
            ttl = exp - now
            if ttl > 0:
                await redis_client.setex(f"token:blacklist:{token}", ttl, "1")
    except Exception:
        pass


async def is_token_blacklisted(token: str) -> bool:
    """주어진 토큰이 Redis 블랙리스트에 등록되어 있는지 조회합니다."""
    try:
        return await redis_client.exists(f"token:blacklist:{token}") > 0
    except Exception:
        return False


def register_user(payload: RegisterRequest, db: Session) -> User:
    if db.query(User).filter(User.email == payload.email).first():
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")
    user = User(email=payload.email, password_hash=hash_password(payload.password))
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def login_user(payload: LoginRequest, db: Session) -> TokenResponse:
    user = db.query(User).filter(User.email == payload.email).first()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
        )
    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def refresh_tokens(refresh_token: str, db: Session) -> TokenResponse:
    if await is_token_blacklisted(refresh_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is blacklisted")

    try:
        payload = decode_token(refresh_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

    if payload.get("type") != "refresh":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")

    return TokenResponse(
        access_token=create_access_token(str(user.id)),
        refresh_token=create_refresh_token(str(user.id)),
    )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    db: Session = Depends(get_db),
) -> User:
    raw_token = credentials.credentials
    if await is_token_blacklisted(raw_token):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token is blacklisted")

    try:
        payload = decode_token(raw_token)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")

    if payload.get("type") != "access":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token type")

    user_id = payload.get("sub")
    user = db.query(User).filter(User.id == uuid.UUID(user_id)).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user
