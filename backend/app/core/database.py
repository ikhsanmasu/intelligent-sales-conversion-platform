from collections.abc import Generator
import logging
import time

from sqlmodel import SQLModel, Session, create_engine, text

from app.core.config import settings

logger = logging.getLogger(__name__)
DB_STARTUP_MAX_ATTEMPTS = 30
DB_STARTUP_RETRY_DELAY_SECONDS = 1.0

app_database_url = settings.app_database_url

app_engine = create_engine(app_database_url)


def _safe_url(value) -> str:
    return value.render_as_string(hide_password=True)


def _wait_for_connection(engine, name: str) -> None:
    last_error: Exception | None = None

    for attempt in range(1, DB_STARTUP_MAX_ATTEMPTS + 1):
        try:
            with engine.connect() as conn:
                conn.execute(text("SELECT 1"))
            return
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            logger.info(
                "Waiting for %s (attempt %d/%d): %s",
                name,
                attempt,
                DB_STARTUP_MAX_ATTEMPTS,
                exc,
            )
            if attempt < DB_STARTUP_MAX_ATTEMPTS:
                time.sleep(DB_STARTUP_RETRY_DELAY_SECONDS)

    if last_error:
        raise last_error


def ensure_app_database_exists() -> None:
    """Ensure the application database connection is reachable."""
    _wait_for_connection(app_engine, "application database")


def get_db() -> Generator[Session, None, None]:
    with Session(app_engine) as session:
        yield session


_ADDITIVE_MIGRATIONS = [
    # Add llm_metadata column to existing chat_messages rows (idempotent).
    "ALTER TABLE chat_messages ADD COLUMN IF NOT EXISTS llm_metadata TEXT",
]


def _run_migrations() -> None:
    with app_engine.begin() as conn:
        for sql in _ADDITIVE_MIGRATIONS:
            try:
                conn.execute(text(sql))
            except Exception as exc:  # noqa: BLE001
                logger.warning("Migration skipped (%s): %s", sql[:60], exc)


def init_app_database() -> None:
    logger.info("Initializing app database on %s", _safe_url(app_engine.url))
    ensure_app_database_exists()

    from app.modules.admin.models import AdminConfig, PromptOverride
    from app.modules.billing.models import LLMUsageEvent
    from app.modules.chatbot.models import (
        Conversation,
        ConversationHistory,
        ConversationMessage,
    )
    from app.agents.memory.models import AgentMemory

    _ = (
        AdminConfig,
        PromptOverride,
        Conversation,
        ConversationMessage,
        ConversationHistory,
        LLMUsageEvent,
        AgentMemory,
    )
    SQLModel.metadata.create_all(app_engine)
    _run_migrations()
    logger.info("Application tables are ready on %s", _safe_url(app_engine.url))


def close_app_database() -> None:
    app_engine.dispose()
    logger.info("Application database engine disposed.")
