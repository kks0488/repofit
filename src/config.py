from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str

    gemini_api_key: str
    gemini_model: str = "gemini-2.5-flash-preview-05-20"

    github_token: str = ""

    # Slack Bot
    slack_bot_token: str = ""
    slack_app_token: str = ""  # Socket Mode (xapp-...)
    slack_channel_id: str = ""
    slack_notify_threshold: float = 0.7

    log_level: str = "INFO"


@lru_cache
def get_settings() -> Settings:
    return Settings()
