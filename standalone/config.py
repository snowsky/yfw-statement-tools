from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # YFW connection
    yfw_api_url: str = "http://localhost:8000"
    yfw_api_key: str = ""

    # Auth
    secret_key: str = "change-me-in-production"

    # Downloads
    download_expiry_minutes: int = 60
    temp_dir: str = "/tmp/statement-tools"

    # Server
    api_port: int = 8000
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
