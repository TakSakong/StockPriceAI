from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    DATABASE_URL: str = "postgresql://stockai:stockai@postgres:5432/stockai"

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"

    # Auth
    SECRET_KEY: str  # 반드시 환경변수로 설정 필요 원래 있던 문자열로 jwt 토큰 생성 가능함.
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 8 # 8시간
    REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # Services
    ML_SERVICE_URL: str = "http://ml:8001"

    # CORS
    CORS_ORIGINS: list[str] = [
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1",
        "http://127.0.0.1:3000",
    ]


settings = Settings()
