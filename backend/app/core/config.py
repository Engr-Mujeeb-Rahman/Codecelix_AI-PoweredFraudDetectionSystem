from functools import lru_cache
from typing import Optional

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Application settings loaded from environment / backend/.env"""

    APP_NAME: str = "Fraud & Risk Detection Platform"
    DEBUG: bool = True

    # Database
    DATABASE_URL: str = "postgresql+psycopg2://postgres:postgres@localhost:5432/fraud_detection"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Security / JWT
    SECRET_KEY: str = "change-me-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24

    # API auth (external businesses)
    API_KEY_HEADER: str = "X-API-Key"
    API_KEY_SALT: str = "fraud-platform-api-key-salt"

    # CORS
    CORS_ORIGINS: str = "http://localhost:3000,http://localhost:5173"

    # Internal worker key
    WORKER_API_KEY: Optional[str] = None

    # LLM settings
    LLM_PROVIDER: str = "gemini"
    GEMINI_API_KEY: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None

    # Cache & Background Tasks
    REDIS_URL: str = "redis://localhost:6379/0"
    CELERY_BROKER_URL: str = "redis://localhost:6379/0"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/0"

    # Risk Engine Thresholds
    RISK_THRESHOLD_LOW: float = 30.0
    RISK_THRESHOLD_HIGH: float = 70.0
    CRITICAL_RISK_THRESHOLD: float = 85.0

    class Config:
        env_file = (".env", "backend/.env")
        env_file_encoding = "utf-8"
        case_sensitive = True
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
