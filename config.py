from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Telegram
    telegram_bot_token: str
    telegram_webhook_url: str

    # Database
    database_url: str

    # Google Sheets
    google_service_account_json: str = "/app/google_credentials.json"

    # DeepSeek AI (OpenAI-compatible)
    deepseek_api_key: str
    deepseek_base_url: str = "https://api.deepseek.com"

    # App
    log_level: str = "INFO"
    timezone_default: str = "Europe/Moscow"
    reminder_default_minutes: int = 30
    evening_report_hour: int = 21
    weekly_report_weekday: int = 6
    weekly_report_hour: int = 20


settings = Settings()
