from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    yfw_api_url: str = "http://localhost:8000"
    yfw_api_key: str = ""
    secret_key: str = "change-me-in-production"
    download_expiry_minutes: int = 60
    temp_dir: str = "/tmp/statement-tools"
    api_port: int = 8000
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
