from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Standalone mode: connect to a YFW instance via HTTP
    yfw_api_url: str = "http://api:8000"
    yfw_api_key: str = ""

    # Standalone mode: protect this service's own API
    # Leave blank for open dev access.
    statement_tools_api_key: str = ""

    download_expiry_minutes: int = 60
    temp_dir: str = "/tmp/statement-tools"
    cors_origins: list[str] = ["*"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
