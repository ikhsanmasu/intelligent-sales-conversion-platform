from pathlib import Path
from urllib.parse import quote_plus

from pydantic_settings import BaseSettings
from dotenv import load_dotenv

ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
load_dotenv(dotenv_path=ENV_FILE)


class Settings(BaseSettings):
    # Chatbot
    CHATBOT_DEFAULT_LLM: str = "openai"
    CHATBOT_DEFAULT_MODEL: str = "gpt-5.2"
    OPENAI_API_KEY: str = ""
    GOOGLE_API_KEY: str = ""
    XAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: str = ""

    # Vector DB
    VECTORDB_PROVIDER: str = "memory"
    VECTORDB_URL: str = ""
    VECTORDB_API_KEY: str = ""
    VECTORDB_COLLECTION: str = "default"
    VECTORDB_INDEX: str = ""
    VECTORDB_NAMESPACE: str = ""

    # Web Search
    WEB_SEARCH_PROVIDER: str = "serper"
    WEB_SEARCH_API_KEY: str = ""
    WEB_SEARCH_API_URL: str = ""
    WEB_BROWSE_MAX_RESULTS: int = 5
    WEB_BROWSE_MAX_PAGES: int = 3
    WEB_BROWSE_MAX_CHARS: int = 4000
    WEB_BROWSE_TIMEOUT: int = 12
    WEB_BROWSE_USER_AGENT: str = "agentic-chatbot/1.0"

    # Application DB (chat history persistence)
    APP_DATABASE_URL: str = ""
    DATABASE_URL: str = ""
    POSTGRES_HOST: str = "localhost"
    POSTGRES_PORT: int = 5432
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "postgres"
    POSTGRES_DB: str = "agentic_chatbot"
    POSTGRES_DRIVER: str = "psycopg"

    # ClickHouse
    CLICKHOUSE_HOST: str = "192.168.100.19"
    CLICKHOUSE_PORT: int = 8722
    CLICKHOUSE_USER: str = "admin"
    CLICKHOUSE_PASSWORD: str = "adminadmin123"
    CLICKHOUSE_DB: str = "default"

    @property
    def clickhouse_url(self) -> str:
        return (
            f"clickhousedb://{self.CLICKHOUSE_USER}:{self.CLICKHOUSE_PASSWORD}"
            f"@{self.CLICKHOUSE_HOST}:{self.CLICKHOUSE_PORT}/{self.CLICKHOUSE_DB}"
        )

    @property
    def app_database_url(self) -> str:
        if self.APP_DATABASE_URL:
            return self.APP_DATABASE_URL
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return self.postgres_url

    @property
    def postgres_url(self) -> str:
        host = self.POSTGRES_HOST.strip()
        database = self.POSTGRES_DB.strip()
        username = self.POSTGRES_USER.strip()
        if not host or not database or not username:
            raise ValueError(
                "POSTGRES_HOST, POSTGRES_DB, and POSTGRES_USER must be set "
                "when APP_DATABASE_URL/DATABASE_URL are not provided."
            )

        encoded_user = quote_plus(username)
        encoded_password = quote_plus(self.POSTGRES_PASSWORD)
        if self.POSTGRES_PASSWORD:
            auth = f"{encoded_user}:{encoded_password}"
        else:
            auth = encoded_user

        return (
            f"postgresql+{self.POSTGRES_DRIVER}://"
            f"{auth}@{host}:{self.POSTGRES_PORT}/{database}"
        )

    @property
    def database_url(self) -> str:
        # Backward-compatible alias used by older code paths.
        return self.clickhouse_url

    class Config:
        env_file = str(ENV_FILE)
        extra = "ignore"


settings = Settings()
