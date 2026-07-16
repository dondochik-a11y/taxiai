from pydantic_settings import BaseSettings, SettingsConfigDict


class BotSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    telegram_bot_token: str = ""
    api_base_url: str = "http://localhost:8000"
    poll_interval_seconds: int = 90
    # FSM storage backend; empty → in-memory fallback (state lost on restart).
    redis_url: str = ""


settings = BotSettings()
