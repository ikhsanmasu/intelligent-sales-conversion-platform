from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(dotenv_path=ENV_FILE)


class Settings(BaseSettings):
    # Public base URL (used for WhatsApp/Telegram image links)
    PUBLIC_BASE_URL: str = ""

    # Chatbot
    CHATBOT_DEFAULT_LLM: str = "openai"
    CHATBOT_DEFAULT_MODEL: str = "gpt-5.2"
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    XAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_WEBHOOK_SECRET: str = ""
    WHATSAPP_VERIFY_TOKEN: str = ""
    WHATSAPP_ACCESS_TOKEN: str = ""
    WHATSAPP_PHONE_NUMBER_ID: str = ""
    WHATSAPP_API_VERSION: str = "v22.0"

    # Application DB (chat history persistence)
    APP_DATABASE_URL: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "agentic_chatbot"
    POSTGRES_SSLMODE: str = "disable"

    @staticmethod
    def _is_placeholder_database_url(value: str) -> bool:
        normalized = value.lower()
        placeholder_tokens = (
            "project-ref",
            "your-db-password",
        )
        return any(token in normalized for token in placeholder_tokens)

    def _derive_postgres_database_url(self) -> str:
        host = (self.POSTGRES_HOST or "").strip()
        username = (self.POSTGRES_USER or "").strip()
        database = (self.POSTGRES_DB or "").strip()
        if not host or not username or not database:
            return ""

        encoded_user = quote_plus(username)
        encoded_password = quote_plus(self.POSTGRES_PASSWORD or "")
        auth = f"{encoded_user}:{encoded_password}" if self.POSTGRES_PASSWORD else encoded_user

        base = (
            f"postgresql+psycopg://{auth}"
            f"@{host}:{int(self.POSTGRES_PORT or 5432)}/{database}"
        )
        sslmode = (self.POSTGRES_SSLMODE or "").strip()
        if sslmode:
            return f"{base}?sslmode={sslmode}"
        return base

    @property
    def app_database_url(self) -> str:
        configured_url = (self.APP_DATABASE_URL or "").strip()
        if configured_url:
            if self._is_placeholder_database_url(configured_url):
                raise ValueError(
                    "APP_DATABASE_URL still contains placeholder values. "
                    "Set a real APP_DATABASE_URL or leave it empty to use POSTGRES_*."
                )
            return configured_url

        derived_url = self._derive_postgres_database_url()
        if derived_url:
            return derived_url

        raise ValueError(
            "Database configuration is missing. Set APP_DATABASE_URL or "
            "POSTGRES_HOST/POSTGRES_PORT/POSTGRES_USER/POSTGRES_PASSWORD/POSTGRES_DB."
        )

    @property
    def database_url(self) -> str:
        # Backward-compatible alias used by older code paths.
        return self.app_database_url

    class Config:
        env_file = str(ENV_FILE)
        extra = "ignore"


settings = Settings()
