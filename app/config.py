from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # Core
    secret_key: str = "change-me-to-a-random-string"
    database_url: str = "postgresql+asyncpg://aso_user:aso_pass@postgres:5432/aso_db"
    database_url_sync: str = "postgresql://aso_user:aso_pass@postgres:5432/aso_db"
    redis_url: str = "redis://redis:6379/0"

    # API Keys (overridable from DB via Settings UI)
    anthropic_api_key: str = ""
    openai_api_key: str = ""
    google_service_account_json: str = ""
    google_play_package_name: str = "com.NetSafe.VPN"
    google_api_discovery_url: str = ""
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""
    serpapi_key: str = ""

    # Defaults (overridable via UI)
    dry_run: bool = True
    max_publish_per_day: int = 1
    max_publish_per_week: int = 5
    auto_approve_threshold: int = 1

    # JWT
    access_token_expire_minutes: int = 60 * 24  # 24 hours

    model_config = {"env_file": ".env", "extra": "ignore"}


@lru_cache
def get_settings() -> Settings:
    return Settings()
