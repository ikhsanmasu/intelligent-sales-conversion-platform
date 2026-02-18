import json
import logging
import re
from collections.abc import Generator
from typing import Any

from app.agents.base import AgentResult, BaseAgent
from app.agents.database.agent import DatabaseAgent
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)

MAX_CHECKS = 5
MAX_ROWS = 50


class AlertAgent(BaseAgent):
    """Agent that checks operational thresholds and generates prioritised alerts.

    Flow:
    1. LLM plans which checks to run (water quality, KPIs, active alerts, etc.)
    2. DatabaseAgent fetches data for each check
    3. LLM analyses all data against domain thresholds and produces
       prioritised alerts with recommended actions
    """

    def __init__(self, llm: BaseLLM, database_agent: DatabaseAgent):
        super().__init__(llm)
        self.database_agent = database_agent

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

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

    @staticmethod
    def _parse_table(output: str) -> tuple[list[str], list[list[str]]]:
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
    def _table_to_text(columns: list[str], rows: list[list[str]]) -> str:
        if not columns:
            return "(no data)"
        header = " | ".join(columns)
        sep = "-+-".join("-" * len(c) for c in columns)
        lines = [header, sep]
        for row in rows[:MAX_ROWS]:
            lines.append(" | ".join(row))
        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Prompt builders
    # ------------------------------------------------------------------

    def _build_plan_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("alert_plan_system")},
            {"role": "user", "content": resolve_prompt("alert_plan_user").format(message=user_message)},
        ]

    def _build_evaluate_messages(
        self, question: str, checks: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("alert_evaluate_system")},
            {
                "role": "user",
                "content": resolve_prompt("alert_evaluate_user").format(
                    question=question,
                    checks=json.dumps(checks, ensure_ascii=False, default=str),
                ),
            },
        ]

    def _parse_plan(self, raw_text: str) -> dict[str, Any] | None:
        raw = self._strip_json_fence(self._strip_think_tags(raw_text))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        checks = payload.get("checks")
        if not isinstance(checks, list) or not checks:
            return None
        payload["checks"] = checks[:MAX_CHECKS]
        return payload

    # ------------------------------------------------------------------
    # execute()
    # ------------------------------------------------------------------

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        question = input_text.strip()
        if not question:
            return AgentResult(output="Error: Empty query.", metadata={"error": "empty query"})

        # Step 1: Plan which checks to run
        plan_messages = self._build_plan_messages(question)
        plan_response = self.llm.generate(
            messages=plan_messages, config=GenerateConfig(temperature=0)
        )
        plan = self._parse_plan(plan_response.text)
        if not plan:
            return AgentResult(
                output="Error: Failed to create alert check plan.",
                metadata={"error": "plan"},
            )

        # Step 2: Execute each check via DatabaseAgent
        check_results: list[dict[str, Any]] = []
        for check in plan.get("checks", [])[:MAX_CHECKS]:
            title = str(check.get("title") or "Check")
            instruction = str(check.get("instruction") or "").strip()
            threshold = check.get("threshold", "")

            if not instruction:
                check_results.append({"title": title, "error": "Instruksi kosong."})
                continue

            db_result = self.database_agent.execute(instruction)
            if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
                check_results.append({
                    "title": title,
                    "instruction": instruction,
                    "threshold": threshold,
                    "error": str(db_result.output),
                })
                continue

            columns, rows = self._parse_table(db_result.output)
            check_results.append({
                "title": title,
                "instruction": instruction,
                "threshold": threshold,
                "columns": columns,
                "rows": rows[:MAX_ROWS],
                "row_count": len(rows),
                "data_text": self._table_to_text(columns, rows),
            })

        # Step 3: LLM evaluates all data against thresholds
        eval_messages = self._build_evaluate_messages(question, check_results)
        eval_response = self.llm.generate(messages=eval_messages)
        interpretation = self._strip_think_tags(eval_response.text)

        return AgentResult(
            output=interpretation,
            metadata={
                "plan": plan,
                "checks": check_results,
            },
        )

    # ------------------------------------------------------------------
    # execute_stream()
    # ------------------------------------------------------------------

    def execute_stream(
        self, input_text: str, context: dict | None = None
    ) -> Generator[dict, None, None]:
        question = input_text.strip()
        if not question:
            yield {"type": "content", "content": "Error: Empty query."}
            return

        # Step 1: Plan
        yield {"type": "thinking", "content": "Merencanakan pemeriksaan alert...\n"}
        plan_messages = self._build_plan_messages(question)
        plan_response = self.llm.generate(
            messages=plan_messages, config=GenerateConfig(temperature=0)
        )
        plan = self._parse_plan(plan_response.text)
        if not plan:
            yield {"type": "content", "content": "Error: Failed to create alert check plan."}
            return

        checks = plan.get("checks", [])[:MAX_CHECKS]
        yield {
            "type": "thinking",
            "content": f"Rencana: {len(checks)} pemeriksaan akan dijalankan.\n\n",
        }

        # Step 2: Execute checks
        check_results: list[dict[str, Any]] = []
        for idx, check in enumerate(checks, start=1):
            title = str(check.get("title") or f"Check {idx}")
            instruction = str(check.get("instruction") or "").strip()
            threshold = check.get("threshold", "")

            yield {"type": "thinking", "content": f"Memeriksa: {title}\n"}

            if not instruction:
                check_results.append({"title": title, "error": "Instruksi kosong."})
                continue

            db_result = self.database_agent.execute(instruction)
            if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
                check_results.append({
                    "title": title,
                    "instruction": instruction,
                    "threshold": threshold,
                    "error": str(db_result.output),
                })
                continue

            columns, rows = self._parse_table(db_result.output)
            check_results.append({
                "title": title,
                "instruction": instruction,
                "threshold": threshold,
                "columns": columns,
                "rows": rows[:MAX_ROWS],
                "row_count": len(rows),
                "data_text": self._table_to_text(columns, rows),
            })

        # Step 3: Evaluate — stream the interpretation
        yield {"type": "thinking", "content": "Menganalisis hasil pemeriksaan...\n"}

        from app.agents.planner.streaming import parse_think_tags

        eval_messages = self._build_evaluate_messages(question, check_results)
        chunks = self.llm.generate_stream(messages=eval_messages)
        for event in parse_think_tags(chunks):
            yield event

        result = AgentResult(
            output="",
            metadata={"plan": plan, "checks": check_results},
        )
        yield {"type": "_result", "data": result}
