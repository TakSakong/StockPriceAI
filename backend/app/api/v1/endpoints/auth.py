from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.auth import LoginRequest, RefreshRequest, RegisterRequest, TokenResponse, UserOut
from app.services.auth import get_current_user, login_user, refresh_tokens, register_user

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201, summary="회원가입")
def register(payload: RegisterRequest, db: Session = Depends(get_db)) -> UserOut:
    """새로운 사용자를 등록(회원가입)합니다.
    이메일 중복 여부를 확인한 후, 비밀번호를 해싱하여 데이터베이스에 유저 정보를 저장합니다.

    Args:
        payload (RegisterRequest): 가입할 사용자의 정보 (email, password).
        db (Session): 데이터베이스 세션 객체.

    Returns:
        UserOut: 생성된 사용자의 정보 (ID, email).

    Raises:
        HTTPException: 이메일이 이미 등록되어 있는 경우 409 Conflict 발생.
    """
    user = register_user(payload, db)
    return UserOut.model_validate(user)


@router.post("/login", response_model=TokenResponse, summary="로그인 (JWT 발급)")
def login(payload: LoginRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """사용자 로그인을 처리하고 JWT 토큰을 발급합니다.
    이메일과 비밀번호를 검증한 후, Access Token과 Refresh Token을 생성하여 반환합니다.

    Args:
        payload (LoginRequest): 로그인 정보 (email, password).
        db (Session): 데이터베이스 세션 객체.

    Returns:
        TokenResponse: 발급된 토큰 세트 (access_token, refresh_token, token_type).

    Raises:
        HTTPException: 자격 증명이 유효하지 않은 경우 401 Unauthorized 발생.
    """
    return login_user(payload, db)


@router.post("/refresh", response_model=TokenResponse, summary="Access Token 재발급")
def refresh(payload: RefreshRequest, db: Session = Depends(get_db)) -> TokenResponse:
    """Refresh Token을 사용하여 새로운 Access Token을 재발급합니다.
    기존 Refresh Token의 유효성을 검사하고, 유효한 경우 새로운 토큰 세트를 반환합니다.

    Args:
        payload (RefreshRequest): Refresh Token 문자열.
        db (Session): 데이터베이스 세션 객체.

    Returns:
        TokenResponse: 재발급된 새로운 토큰 세트.

    Raises:
        HTTPException: 토큰이 만료되었거나 유효하지 않은 경우 401 Unauthorized 발생.
    """
    return refresh_tokens(payload.refresh_token, db)


@router.get("/me", response_model=UserOut, summary="현재 로그인 사용자 조회")
def me(current_user=Depends(get_current_user)) -> UserOut:
    """현재 로그인한 사용자의 정보를 조회합니다.
    요청 헤더의 Bearer 토큰을 통해 사용자를 식별하고 정보를 반환합니다.

    Args:
        current_user (User): 인증된 현재 사용자 객체 (종속성 주입).

    Returns:
        UserOut: 현재 사용자의 정보 (ID, email).
    """
    return UserOut.model_validate(current_user)
