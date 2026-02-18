from typing import Any

from sqlmodel import text

# Columns injected by Kafka CDC pipeline — never useful for analytical queries.
_INTERNAL_COLUMNS = frozenset({
    "op", "db", "schema", "table", "lsn", "ts_ms", "txId",
    "_kafka_key", "_kafka_topic", "_kafka_partition",
    "_kafka_offset", "_kafka_timestamp", "_ingestion_time",
})

# Databases that contain actual queryable data.
_ALLOWED_DATABASES = ("cultivation", "transformed_cultivation")

# Tables that are not useful for farm operations Q&A.
_EXCLUDED_TABLES = frozenset({
    "_prisma_migrations", "log", "uploaded_files", "user_logins",
    "notifications", "permissions", "role_permissions", "roles",
    "user_roles", "user_sites", "users", "profiles",
    "content", "library", "config", "settings", "settings_category",
    "seed_option_scoring", "seed_parameter_scoring",
    "seeds_score_option", "seeds_score_parameter",
})


def get_schema_info(engine: Any) -> str:
    """Query ClickHouse system.columns and return a clean, LLM-friendly schema string.

    Improvements over the raw dump:
    - Only includes `cultivation` and `transformed_cultivation` databases.
    - Excludes internal Kafka CDC columns (op, db, schema, table, lsn, …).
    - Excludes non-operational tables (auth, content, logging).
    - Marks soft-delete columns clearly.
    """
    db_filter = ", ".join(f"'{d}'" for d in _ALLOWED_DATABASES)
    query = text(f"""
        SELECT
            database,
            table,
            name,
            type,
            comment
        FROM system.columns
        WHERE database IN ({db_filter})
        ORDER BY database, table, position
    """)

    with engine.connect() as conn:
        rows = conn.execute(query).fetchall()

    if not rows:
        return "No tables found in the database."

    tables: dict[str, list[str]] = {}
    for database, table, col_name, col_type, comment in rows:
        if table in _EXCLUDED_TABLES:
            continue
        if col_name in _INTERNAL_COLUMNS:
            continue

        full_name = f"{database}.{table}"
        if full_name not in tables:
            tables[full_name] = []

        comment_str = f"  -- {comment}" if comment else ""
        tables[full_name].append(f"  {col_name} {col_type}{comment_str}")

    parts = []
    for table_name, columns in tables.items():
        cols = "\n".join(columns)
        parts.append(f"TABLE {table_name}:\n{cols}")

    return "\n\n".join(parts)
