"""Application configuration loaded from environment variables."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Holds configuration values used by the backend.

    Values can be supplied through environment variables or a local `.env` file.
    Keeping secrets in configuration rather than source code makes deployment safer.
    """

    app_name: str = "EkoMatik Backend"
    database_url: str = "postgresql+psycopg2://ekomatik:ekomatik@localhost:5432/ekomatik"
    hmac_secret_key: str = "CHANGE_ME_HMAC_SECRET"
    jwt_secret_key: str = "CHANGE_ME_JWT_SECRET"
    hmac_max_age_seconds: int = 10
    jwt_algorithm: str = "HS256"
    max_vision_file_size_mb: int = 10

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()