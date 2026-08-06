from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application configuration loaded from .env.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

    port: int = Field(default=8000, alias="PORT")

    environment: str = Field(
        default="development",
        alias="ENVIRONMENT",
    )

    database_url: str = Field(
        alias="DATABASE_URL",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Return cached settings instance.
    """
    return Settings()


settings = get_settings()