"""
OWNER: Person A
Loads settings from .env via pydantic-settings.
Redis is optional — Person A/B do not require it at startup.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://nyayaos:nyayaos@localhost:5432/nyayaos"
    JWT_SECRET_KEY: str = "dev-insecure-change-me"
    JWT_ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60

    # Optional — not required for Person A/B or app startup
    REDIS_URL: str | None = "redis://localhost:6379/0"

    # Gemini (optional until an AI route calls the service)
    GEMINI_API_KEY: str | None = None
    GEMINI_MODEL: str = "gemini-2.5-flash"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
