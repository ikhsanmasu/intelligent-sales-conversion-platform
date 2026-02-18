import json
import logging
import re
from collections.abc import Generator
from typing import Any

from app.agents.base import AgentResult, BaseAgent
from app.agents.database import DatabaseAgent
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)


class ChartAgent(BaseAgent):
    def __init__(self, llm: BaseLLM, database_agent: DatabaseAgent):
        super().__init__(llm)
        self.database_agent = database_agent

    @staticmethod
    def _strip_json_fence(raw_text: str) -> str:
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return raw

    @staticmethod
    def _strip_think_tags(raw_text: str) -> str:
        cleaned = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL)
        return cleaned.strip()

    def _build_db_command_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("chart_db_command_system")},
            {"role": "user", "content": resolve_prompt("chart_db_command_user").format(message=user_message)},
        ]

    def _build_chart_spec_messages(
        self, question: str, columns: list[str], rows: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("chart_spec_system")},
            {
                "role": "user",
                "content": resolve_prompt("chart_spec_user").format(
                    question=question,
                    columns=", ".join(columns),
                    rows=json.dumps(rows, ensure_ascii=False),
                ),
            },
        ]

    @staticmethod
    def _parse_table(output: str) -> tuple[list[str], list[list[str]], str]:
        """Parse pipe-delimited table from DatabaseAgent output.

        Returns (columns, rows, parse_hint) where parse_hint explains
        why parsing failed (empty string on success).
        """
        if "(no rows returned)" in output:
            return [], [], "Database returned no rows for this query."
        parts = output.split("\n\n")
        if len(parts) < 2:
            return [], [], f"Unexpected DB output format (no table section). Raw: {output[:200]}"
        table_block = parts[-1].strip()
        if not table_block:
            return [], [], "Table section is empty."
        if table_block.startswith("Error:"):
            return [], [], f"DB error: {table_block[:200]}"
        lines = [line for line in table_block.splitlines() if line.strip()]
        if len(lines) < 2:
            return [], [], f"Table has fewer than 2 lines. Got: {table_block[:200]}"
        columns = [c.strip() for c in lines[0].split(" | ")]
        rows: list[list[str]] = []
        for line in lines[2:]:
            row = [c.strip() for c in line.split(" | ")]
            if len(row) != len(columns):
                continue
            rows.append(row)
        if not rows:
            return columns, [], f"Parsed header ({', '.join(columns)}) but no valid data rows."
        return columns, rows, ""

    @staticmethod
    def _rows_to_objects(columns: list[str], rows: list[list[str]]) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for row in rows:
            obj = {columns[idx]: row[idx] for idx in range(len(columns))}
            results.append(obj)
        return results

    @staticmethod
    def _coerce_number(value: Any) -> float | None:
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value)
        raw = str(value).strip().replace(",", "")
        if not raw:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    def _fallback_spec(self, question: str, columns: list[str], rows: list[list[str]]) -> dict[str, Any]:
        if not columns or not rows:
            return {"error": "No data available to build chart."}

        x_idx = 0
        y_idx = None
        for idx in range(len(columns)):
            if idx == x_idx:
                continue
            if any(self._coerce_number(row[idx]) is not None for row in rows):
                y_idx = idx
                break
        if y_idx is None:
            return {"error": "No numeric column found for chart values."}

        data = []
        for row in rows[:20]:
            x_val = row[x_idx]
            y_val = self._coerce_number(row[y_idx])
            if y_val is None:
                continue
            data.append({"x": str(x_val), "y": y_val})

        if not data:
            return {"error": "No usable numeric data for chart."}

        return {
            "chart": {
                "type": "bar",
                "title": question[:80] if question else "Chart",
                "x_label": columns[x_idx],
                "y_label": columns[y_idx],
                "series": [
                    {
                        "name": columns[y_idx],
                        "data": data,
                    }
                ],
            }
        }

    def _build_chart_spec(
        self, question: str, columns: list[str], rows: list[list[str]]
    ) -> dict[str, Any]:
        row_objects = self._rows_to_objects(columns, rows[:30])
        messages = self._build_chart_spec_messages(question, columns, row_objects)
        response = self.llm.generate(messages=messages, config=GenerateConfig(temperature=0))
        raw = self._strip_json_fence(response.text)
        try:
            payload = json.loads(raw)
            if isinstance(payload, dict):
                return payload
        except json.JSONDecodeError:
            logger.warning("Failed to parse chart spec JSON, falling back.")
        return self._fallback_spec(question, columns, rows)

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        question = input_text.strip()
        if not question:
            return AgentResult(output="Error: Empty query.", metadata={"error": "empty query"})

        command_messages = self._build_db_command_messages(question)
        command_response = self.llm.generate(messages=command_messages, config=GenerateConfig(temperature=0))
        db_instruction = self._strip_think_tags(command_response.text)

        db_result = self.database_agent.execute(db_instruction)
        if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
            return AgentResult(
                output=f"Error: {db_result.output}",
                metadata={
                    "error": db_result.output,
                    "db_instruction": db_instruction,
                    **db_result.metadata,
                },
            )

        columns, rows, parse_hint = self._parse_table(db_result.output)
        if not columns or not rows:
            error_msg = parse_hint or "No data available to build chart."
            payload = {"error": error_msg}
            return AgentResult(
                output=json.dumps(payload, ensure_ascii=False),
                metadata={"error": error_msg, "db_instruction": db_instruction},
            )

        chart_payload = self._build_chart_spec(question, columns, rows)
        output = json.dumps(chart_payload, ensure_ascii=False)
        return AgentResult(
            output=output,
            metadata={
                "chart": chart_payload.get("chart"),
                "db_instruction": db_instruction,
                "columns": columns,
                "row_count": len(rows),
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        question = input_text.strip()
        if not question:
            yield {"type": "content", "content": "Error: Empty query."}
            return

        yield {"type": "thinking", "content": "Menyusun instruksi data chart...\n"}
        command_messages = self._build_db_command_messages(question)
        command_response = self.llm.generate(messages=command_messages, config=GenerateConfig(temperature=0))
        db_instruction = self._strip_think_tags(command_response.text)
        yield {"type": "thinking", "content": f"Instruksi DB: {db_instruction}\n\n"}

        yield {"type": "thinking", "content": "Menarik data dari database...\n"}
        db_result = self.database_agent.execute(db_instruction)

        if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
            yield {"type": "thinking", "content": f"Error dari database: {str(db_result.output)[:300]}\n\n"}
            yield {"type": "content", "content": f"Error: {db_result.output}"}
            return

        # Show DB output in thinking for debugging
        db_output_str = str(db_result.output)
        # Show SQL (first line) and the table part (after blank line)
        parts = db_output_str.split("\n\n", 1)
        header_part = parts[0][:300] if parts else ""
        table_part = parts[1][:400] if len(parts) > 1 else "(no table section)"
        yield {"type": "thinking", "content": f"DB output header:\n{header_part}\n\nDB output table:\n{table_part}\n\n"}

        columns, rows, parse_hint = self._parse_table(db_result.output)
        if not columns or not rows:
            error_msg = parse_hint or "No data available to build chart."
            yield {"type": "thinking", "content": f"Parse gagal: {error_msg}\n\n"}
            payload = {"error": error_msg}
            result = AgentResult(
                output=json.dumps(payload, ensure_ascii=False),
                metadata={"error": error_msg, "db_instruction": db_instruction},
            )
            yield {"type": "_result", "data": result}
            return

        yield {"type": "thinking", "content": f"Data parsed: {len(rows)} baris, kolom: {', '.join(columns)}\n\n"}
        yield {"type": "thinking", "content": "Menyusun spesifikasi chart...\n"}
        chart_payload = self._build_chart_spec(question, columns, rows)
        output = json.dumps(chart_payload, ensure_ascii=False)
        result = AgentResult(
            output=output,
            metadata={
                "chart": chart_payload.get("chart"),
                "db_instruction": db_instruction,
                "columns": columns,
                "row_count": len(rows),
            },
        )
        yield {"type": "_result", "data": result}
