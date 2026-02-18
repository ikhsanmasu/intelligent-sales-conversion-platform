from collections.abc import Generator
import logging
import time

from sqlmodel import SQLModel, Session, create_engine, text

from app.core.config import settings

logger = logging.getLogger(__name__)
DB_STARTUP_MAX_ATTEMPTS = 30
DB_STARTUP_RETRY_DELAY_SECONDS = 1.0

clickhouse_engine = create_engine(settings.clickhouse_url)
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
    """Ensure the target application database exists before creating tables."""
    url = app_engine.url

    backend_name = url.get_backend_name()
    if backend_name != "postgresql":
        raise RuntimeError(
            f"Unsupported app database backend '{backend_name}'. PostgreSQL is required."
        )

    # For PostgreSQL, create database if it does not exist yet.
    database_name = url.database
    if not database_name:
        return

    admin_url = url.set(database="postgres")
    admin_engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    try:
        _wait_for_connection(admin_engine, "postgres admin database")

        with admin_engine.connect() as conn:
            exists = conn.execute(
                text("SELECT 1 FROM pg_database WHERE datname = :name"),
                {"name": database_name},
            ).scalar()

            if not exists:
                safe_database_name = database_name.replace('"', '""')
                conn.execute(text(f'CREATE DATABASE "{safe_database_name}"'))
                logger.info(
                    "Created PostgreSQL database '%s' because it did not exist.",
                    database_name,
                )
    finally:
        admin_engine.dispose()

    _wait_for_connection(app_engine, f"application database '{database_name}'")


def get_db() -> Generator[Session, None, None]:
    with Session(app_engine) as session:
        yield session


def init_app_database() -> None:
    logger.info("Initializing app database on %s", _safe_url(app_engine.url))
    ensure_app_database_exists()

    from app.modules.admin.models import AdminConfig, PromptOverride
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
        AgentMemory,
    )
    SQLModel.metadata.create_all(app_engine)
    logger.info("Application tables are ready on %s", _safe_url(app_engine.url))


def close_app_database() -> None:
    app_engine.dispose()
    clickhouse_engine.dispose()
    logger.info("Database engines disposed.")
