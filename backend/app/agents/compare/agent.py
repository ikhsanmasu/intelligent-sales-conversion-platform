import json
import logging
import re
from collections.abc import Generator
from typing import Any

import pandas as pd

from app.agents.base import AgentResult, BaseAgent
from app.agents.database.agent import DatabaseAgent
from app.agents.timeseries.executor import execute_code
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)

MAX_CODEGEN_RETRIES = 2


class CompareAgent(BaseAgent):
    def __init__(self, llm: BaseLLM, database_agent: DatabaseAgent):
        super().__init__(llm)
        self.database_agent = database_agent

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_code_fence(raw_text: str) -> str:
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:python|json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return raw

    @staticmethod
    def _strip_think_tags(raw_text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
        return cleaned.strip()

    @staticmethod
    def _parse_table(output: str) -> tuple[list[str], list[list[str]]]:
        """Parse formatted table output from DatabaseAgent."""
        if "(no rows returned)" in output:
            return [], []
        parts = output.split("\n\n")
        if len(parts) < 2:
            return [], []
        table_block = parts[-1].strip()
        if not table_block or table_block.startswith("Error:"):
            return [], []
        lines = [line for line in table_block.splitlines() if line.strip()]
        if len(lines) < 2:
            return [], []
        columns = [c.strip() for c in lines[0].split(" | ")]
        rows: list[list[str]] = []
        for line in lines[2:]:
            row = [c.strip() for c in line.split(" | ")]
            if len(row) != len(columns):
                continue
            rows.append(row)
        return columns, rows

    @staticmethod
    def _to_dataframe(columns: list[str], rows: list[list[str]]) -> pd.DataFrame:
        """Convert parsed table data into a pandas DataFrame with coercion."""
        df = pd.DataFrame(rows, columns=columns)
        for col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="ignore")
            if df[col].dtype == object:
                try:
                    parsed = pd.to_datetime(df[col], infer_datetime_format=True, errors="coerce")
                    if parsed.notna().sum() > len(df) * 0.5:
                        df[col] = parsed
                except Exception:
                    pass
        return df

    @staticmethod
    def _df_summary(df: pd.DataFrame, max_sample_rows: int = 5) -> str:
        """Build a concise description of the DataFrame for the codegen prompt."""
        lines = [f"Shape: {df.shape[0]} rows x {df.shape[1]} columns"]
        lines.append("Columns and dtypes:")
        for col in df.columns:
            lines.append(f"  - {col}: {df[col].dtype}")
        sample = df.head(max_sample_rows)
        lines.append(f"\nSample rows (first {min(max_sample_rows, len(df))}):")
        lines.append(sample.to_string(index=False))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_cmp_command_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("cmp_command_system")},
            {"role": "user", "content": resolve_prompt("cmp_command_user").format(message=user_message)},
        ]

    def _build_codegen_messages(self, question: str, df_summary: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("cmp_codegen_system")},
            {
                "role": "user",
                "content": resolve_prompt("cmp_codegen_user").format(
                    question=question,
                    df_summary=df_summary,
                ),
            },
        ]

    def _build_interpret_messages(
        self, question: str, code: str, computation_result: dict
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("cmp_interpret_system")},
            {
                "role": "user",
                "content": resolve_prompt("cmp_interpret_user").format(
                    question=question,
                    code=code,
                    result=json.dumps(computation_result, ensure_ascii=False, default=str),
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Code generation with retry
    # ------------------------------------------------------------------

    def _generate_and_execute_code(
        self, question: str, df: pd.DataFrame
    ) -> tuple[str, dict[str, Any]]:
        """Generate comparison code, execute it, retry on failure."""
        summary = self._df_summary(df)
        messages = self._build_codegen_messages(question, summary)
        config = GenerateConfig(temperature=0)

        retry_tpl = resolve_prompt("cmp_codegen_retry")
        last_code = ""

        for attempt in range(1, MAX_CODEGEN_RETRIES + 2):
            response = self.llm.generate(messages=messages, config=config)
            raw_code = self._strip_code_fence(self._strip_think_tags(response.text))
            last_code = raw_code

            exec_result = execute_code(raw_code, {"df": df})

            if "error" not in exec_result:
                return raw_code, exec_result

            if attempt <= MAX_CODEGEN_RETRIES:
                error_msg = exec_result["error"]
                logger.warning("Codegen attempt %d failed: %s", attempt, error_msg)
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
            else:
                return last_code, exec_result

        return last_code, {"error": "Max codegen retries exceeded."}

    # ------------------------------------------------------------------
    # execute() — non-streaming
    # ------------------------------------------------------------------

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        question = input_text.strip()
        if not question:
            return AgentResult(output="Error: Empty query.", metadata={"error": "empty query"})

        # Step 1: Generate DB instruction for comparison data
        command_messages = self._build_cmp_command_messages(question)
        command_response = self.llm.generate(
            messages=command_messages, config=GenerateConfig(temperature=0)
        )
        db_instruction = self._strip_think_tags(command_response.text)

        # Step 2: Fetch data via DatabaseAgent
        db_result = self.database_agent.execute(db_instruction)
        if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
            return AgentResult(
                output=f"Error: {db_result.output}",
                metadata={"error": db_result.output, "db_instruction": db_instruction},
            )

        # Step 3: Parse into DataFrame
        columns, rows = self._parse_table(db_result.output)
        if not columns or not rows:
            return AgentResult(
                output="Error: No data returned from database for comparison.",
                metadata={"error": "no data", "db_instruction": db_instruction},
            )
        df = self._to_dataframe(columns, rows)

        # Step 4-5: Generate code & execute
        code, exec_result = self._generate_and_execute_code(question, df)

        if "error" in exec_result:
            return AgentResult(
                output=f"Error during comparison: {exec_result['error']}",
                metadata={
                    "error": exec_result["error"],
                    "code": code,
                    "db_instruction": db_instruction,
                },
            )

        # Step 6: Interpret results
        interpret_messages = self._build_interpret_messages(
            question, code, exec_result.get("result", {})
        )
        interpret_response = self.llm.generate(messages=interpret_messages)
        interpretation = self._strip_think_tags(interpret_response.text)

        return AgentResult(
            output=interpretation,
            metadata={
                "db_instruction": db_instruction,
                "code": code,
                "computation_result": exec_result.get("result"),
                "stdout": exec_result.get("stdout", ""),
                "columns": columns,
                "row_count": len(rows),
            },
        )

    # ------------------------------------------------------------------
    # execute_stream() — SSE-friendly streaming
    # ------------------------------------------------------------------

    def execute_stream(
        self, input_text: str, context: dict | None = None
    ) -> Generator[dict, None, None]:
        question = input_text.strip()
        if not question:
            yield {"type": "content", "content": "Error: Empty query."}
            return

        # Step 1: Generate DB instruction
        yield {"type": "thinking", "content": "Menyusun instruksi pengambilan data perbandingan...\n"}
        command_messages = self._build_cmp_command_messages(question)
        command_response = self.llm.generate(
            messages=command_messages, config=GenerateConfig(temperature=0)
        )
        db_instruction = self._strip_think_tags(command_response.text)
        yield {"type": "thinking", "content": f"Instruksi DB: {db_instruction}\n\n"}

        # Step 2: Fetch data
        yield {"type": "thinking", "content": "Menarik data dari database...\n"}
        db_result = None
        for event in self.database_agent.execute_stream(db_instruction):
            if event.get("type") == "_result":
                db_result = event["data"]
            else:
                yield event

        if db_result is None:
            yield {"type": "content", "content": "Error: Database agent returned no result."}
            return

        if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
            yield {"type": "content", "content": f"Error: {db_result.output}"}
            return

        # Step 3: Parse into DataFrame
        columns, rows = self._parse_table(db_result.output)
        if not columns or not rows:
            yield {"type": "content", "content": "Error: No data returned from database for comparison."}
            return

        df = self._to_dataframe(columns, rows)
        yield {
            "type": "thinking",
            "content": f"Data tersedia: {len(rows)} baris, {len(columns)} kolom.\n\n",
        }

        # Step 4-5: Generate code & execute (with retry)
        yield {"type": "thinking", "content": "Menghasilkan kode perbandingan...\n"}
        summary = self._df_summary(df)
        messages = self._build_codegen_messages(question, summary)
        config = GenerateConfig(temperature=0)
        retry_tpl = resolve_prompt("cmp_codegen_retry")

        exec_result: dict[str, Any] | None = None
        last_code = ""

        for attempt in range(1, MAX_CODEGEN_RETRIES + 2):
            if attempt > 1:
                yield {
                    "type": "thinking",
                    "content": f"Retry kode perbandingan (percobaan {attempt})...\n",
                }

            response = self.llm.generate(messages=messages, config=config)
            raw_code = self._strip_code_fence(self._strip_think_tags(response.text))
            last_code = raw_code

            yield {"type": "thinking", "content": "Menjalankan kode perbandingan...\n"}
            current_result = execute_code(raw_code, {"df": df})

            if "error" not in current_result:
                exec_result = current_result
                break

            if attempt <= MAX_CODEGEN_RETRIES:
                error_msg = current_result["error"]
                yield {"type": "thinking", "content": f"Eksekusi gagal: {error_msg}\n"}
                messages.append({"role": "assistant", "content": response.text})
                messages.append({"role": "user", "content": retry_tpl.format(error=error_msg)})
            else:
                exec_result = current_result

        if exec_result is None or "error" in exec_result:
            error_msg = (exec_result or {}).get("error", "Unknown error")
            yield {"type": "content", "content": f"Error during comparison: {error_msg}"}
            return

        yield {
            "type": "thinking",
            "content": "Perbandingan selesai. Menyusun interpretasi...\n",
        }

        # Step 6: Interpret results — stream the final answer
        from app.agents.planner.streaming import parse_think_tags

        interpret_messages = self._build_interpret_messages(
            question, last_code, exec_result.get("result", {})
        )
        chunks = self.llm.generate_stream(messages=interpret_messages)
        for event in parse_think_tags(chunks):
            yield event

        result = AgentResult(
            output="",
            metadata={
                "db_instruction": db_instruction,
                "code": last_code,
                "computation_result": exec_result.get("result"),
                "stdout": exec_result.get("stdout", ""),
                "columns": columns,
                "row_count": len(rows),
            },
        )
        yield {"type": "_result", "data": result}
