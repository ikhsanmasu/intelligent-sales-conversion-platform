import json
import logging
import re
from collections.abc import Generator

from sqlmodel import text

from app.agents.base import AgentResult, BaseAgent
from app.agents.database.introspect import get_schema_info
from app.agents.database.schemas import QueryResult
from app.core.database import clickhouse_engine
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)

MAX_RETRIES = 3

FORBIDDEN_KEYWORDS = re.compile(
    r"\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|TRUNCATE|GRANT|REVOKE|EXEC|EXECUTE)\b",
    re.IGNORECASE,
)


class DatabaseAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    def _get_schema(self) -> str:
        return get_schema_info(clickhouse_engine)

    def _parse_llm_response(self, raw: str) -> tuple[str, str]:
        raw = raw.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        parsed = json.loads(raw)
        return parsed["sql"], parsed.get("explanation", "")

    def _validate_sql(self, sql: str) -> None:
        stripped = sql.strip().rstrip(";").strip()
        if not stripped.upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed.")
        if FORBIDDEN_KEYWORDS.search(stripped):
            raise ValueError("Query contains forbidden keywords.")

    def _execute_sql(self, sql: str) -> QueryResult:
        
        with clickhouse_engine.connect() as conn:
            result = conn.execute(text(sql))
            columns = list(result.keys())
            rows = [list(row) for row in result.fetchall()]
            return QueryResult(
                columns=columns,
                rows=rows,
                row_count=len(rows),
                sql=sql,
            )

    def _format_result(self, result: QueryResult, explanation: str) -> str:
        if result.rows:
            header = " | ".join(result.columns)
            separator = "-+-".join("-" * len(c) for c in result.columns)
            lines = [header, separator]
            for row in result.rows[:50]:
                lines.append(" | ".join(str(v) for v in row))
            formatted_rows = "\n".join(lines)
        else:
            formatted_rows = "(no rows returned)"

        return (
            f"SQL: {result.sql}\n"
            f"Explanation: {explanation}\n"
            f"Rows: {result.row_count}\n\n"
            f"{formatted_rows}"
        )

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        schema = self._get_schema()
        config = GenerateConfig(temperature=0)

        messages = [
            {"role": "system", "content": resolve_prompt("nl_to_sql_system").format(schema=schema)},
            {"role": "user", "content": resolve_prompt("nl_to_sql_user").format(question=input_text)},
        ]

        attempts = []
        retry_tpl = resolve_prompt("nl_to_sql_retry")

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                response = self.llm.generate(messages=messages, config=config)
                sql, explanation = self._parse_llm_response(response.text)
            except (json.JSONDecodeError, KeyError) as e:
                error_msg = f"Failed to parse your response as JSON: {e}. Raw output: {response.text[:200]}"
                logger.warning("Attempt %d — parse error: %s", attempt, error_msg)
                attempts.append({"attempt": attempt, "error": error_msg})
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
                continue

            try:
                self._validate_sql(sql)
            except ValueError as e:
                error_msg = f"SQL validation error: {e}. Generated SQL: {sql}"
                logger.warning("Attempt %d — validation error: %s", attempt, error_msg)
                attempts.append({"attempt": attempt, "sql": sql, "error": str(e)})
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
                continue

            try:
                result = self._execute_sql(sql)
            except Exception as e:
                error_msg = f"ClickHouse execution error: {e}. SQL: {sql}"
                logger.warning("Attempt %d — execution error: %s", attempt, error_msg)
                attempts.append({"attempt": attempt, "sql": sql, "error": str(e)})
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
                continue

            output = self._format_result(result, explanation)
            return AgentResult(
                output=output,
                metadata={
                    "sql": result.sql,
                    "row_count": result.row_count,
                    "attempts": attempt,
                },
            )

        last_error = attempts[-1]["error"] if attempts else "Unknown error"
        logger.error("All %d attempts failed for question: %s", MAX_RETRIES, input_text)
        return AgentResult(
            output=f"Error: Failed after {MAX_RETRIES} attempts. Last error: {last_error}",
            metadata={"error": last_error, "attempts": attempts},
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        """Step-by-step streaming with thinking events. Yields a final _result event."""

        yield {"type": "thinking", "content": "Memeriksa skema database...\n"}
        schema = self._get_schema()
        table_count = schema.count("TABLE ")
        yield {"type": "thinking", "content": f"Skema tersedia: {table_count} tabel.\n\n"}

        config = GenerateConfig(temperature=0)
        messages = [
            {"role": "system", "content": resolve_prompt("nl_to_sql_system").format(schema=schema)},
            {"role": "user", "content": resolve_prompt("nl_to_sql_user").format(question=input_text)},
        ]

        final_result = None
        retry_tpl = resolve_prompt("nl_to_sql_retry")

        for attempt in range(1, MAX_RETRIES + 1):
            if attempt > 1:
                yield {"type": "thinking", "content": f"Mencoba ulang... (percobaan {attempt}/{MAX_RETRIES})\n"}

            yield {"type": "thinking", "content": "Menyusun query SQL dari instruksi...\n"}

            # Step 1: Generate
            try:
                response = self.llm.generate(messages=messages, config=config)
                sql, explanation = self._parse_llm_response(response.text)
            except (json.JSONDecodeError, KeyError) as e:
                error_msg = f"Failed to parse your response as JSON: {e}. Raw output: {response.text[:200]}"
                logger.warning("Attempt %d — parse error: %s", attempt, error_msg)
                yield {"type": "thinking", "content": f"Kesalahan parsing: {e}\n"}
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
                continue

            yield {
                "type": "thinking",
                "content": (
                    "Rencana query\n"
                    f"SQL: {sql}\n"
                    f"Alasan: {explanation}\n\n"
                ),
            }

            # Step 2: Validate
            yield {"type": "thinking", "content": "Validasi query (hanya SELECT + cek kata terlarang)...\n"}
            try:
                self._validate_sql(sql)
            except ValueError as e:
                error_msg = f"SQL validation error: {e}. Generated SQL: {sql}"
                logger.warning("Attempt %d — validation error: %s", attempt, error_msg)
                yield {"type": "thinking", "content": f"Validasi gagal: {e}\n"}
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
                continue

            # Step 3: Execute
            yield {"type": "thinking", "content": "Menjalankan query di ClickHouse...\n"}
            try:
                result = self._execute_sql(sql)
            except Exception as e:
                error_msg = f"ClickHouse execution error: {e}. SQL: {sql}"
                logger.warning("Attempt %d — execution error: %s", attempt, error_msg)
                yield {"type": "thinking", "content": f"Eksekusi gagal: {e}\n"}
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
                continue

            # Success
            yield {"type": "thinking", "content": f"Hasil query: {result.row_count} baris.\n"}

            output = self._format_result(result, explanation)
            final_result = AgentResult(
                output=output,
                metadata={"sql": result.sql, "row_count": result.row_count, "attempts": attempt},
            )
            break

        if final_result is None:
            final_result = AgentResult(
                output=f"Error: Failed after {MAX_RETRIES} attempts.",
                metadata={"error": "max retries exceeded"},
            )

        # Internal marker for PlannerAgent to capture the result
        yield {"type": "_result", "data": final_result}
