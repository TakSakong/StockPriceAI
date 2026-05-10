from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserOut
from app.services.auth import get_current_user, login_user, refresh_tokens, register_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201, summary="회원가입")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    user = register_user(payload, db)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="로그인 (JWT 발급)")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return login_user(payload, db)


@router.post("/refresh", response_model=TokenResponse, summary="Access Token 재발급")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    return refresh_tokens(payload.refresh_token, db)


@router.get("/me", response_model=UserOut, summary="현재 로그인 사용자 조회")
def me(current_user=Depends(get_current_user)) -> UserOut:
    return UserOut.model_validate(current_user)
