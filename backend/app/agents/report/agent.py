import json
import logging
import re
from collections.abc import Generator
from typing import Any

from sqlmodel import text

from app.agents.base import AgentResult, BaseAgent
from app.agents.database import DatabaseAgent
from app.core.database import clickhouse_engine
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)

MAX_SECTIONS = 6
MAX_ROWS = 50
GENERIC_SECTION_ERROR = "Data tidak tersedia atau terjadi error sistem."


class ReportAgent(BaseAgent):
    def __init__(self, llm: BaseLLM, database_agent: DatabaseAgent):
        super().__init__(llm)
        self.database_agent = database_agent

    # ------------------------------------------------------------------
    # Entity resolution — fetch real site names so the planner LLM can
    # map user input to exact database names.
    # ------------------------------------------------------------------

    @staticmethod
    def _fetch_entity_context() -> str:
        """Fetch active site names directly from ClickHouse (no LLM call)."""
        try:
            with clickhouse_engine.connect() as conn:
                rows = conn.execute(
                    text(
                        "SELECT DISTINCT name "
                        "FROM cultivation.sites AS s FINAL "
                        "WHERE s.deleted_by = 0 AND s.status = 1 "
                        "ORDER BY name"
                    )
                ).fetchall()
            site_names = [str(row[0]) for row in rows if row[0]]
            if not site_names:
                return ""
            return (
                "SITE AKTIF DI DATABASE:\n"
                + ", ".join(site_names)
                + "\n\n"
                "Jika user menyebut nama site secara parsial atau tidak tepat, "
                "cocokkan ke nama LENGKAP dari daftar di atas.\n"
                "Gunakan nama PERSIS dari daftar di atas di setiap instruction."
            )
        except Exception as exc:
            logger.warning("Failed to fetch entity context: %s", exc)
            return ""

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

    # ------------------------------------------------------------------
    # Message builders
    # ------------------------------------------------------------------

    def _build_plan_messages(self, user_message: str, entity_context: str = "") -> list[dict[str, str]]:
        system_content = resolve_prompt("report_plan_system")
        if entity_context:
            system_content += "\n\n" + entity_context
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": resolve_prompt("report_plan_user").format(message=user_message)},
        ]

    def _build_compile_messages(
        self, question: str, plan: dict[str, Any], sections: list[dict[str, Any]]
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("report_compile_system")},
            {
                "role": "user",
                "content": resolve_prompt("report_compile_user").format(
                    question=question,
                    plan=json.dumps(plan, ensure_ascii=False),
                    sections=json.dumps(sections, ensure_ascii=False),
                ),
            },
        ]

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    def _parse_plan(self, raw_text: str) -> dict[str, Any] | None:
        raw = self._strip_json_fence(self._strip_think_tags(raw_text))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return None
        if not isinstance(payload, dict):
            return None
        sections = payload.get("sections")
        if not isinstance(sections, list) or not sections:
            return None
        payload["sections"] = sections[:MAX_SECTIONS]
        payload.setdefault("format", "markdown")
        payload.setdefault("title", "Laporan Operasional")
        payload.setdefault("period", "")
        return payload

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
            return [], [], f"Unexpected DB output format. Raw: {output[:200]}"
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
    def _table_to_markdown(columns: list[str], rows: list[list[str]]) -> str:
        if not columns:
            return "_(no data)_"
        header = "| " + " | ".join(columns) + " |"
        sep = "| " + " | ".join(["---"] * len(columns)) + " |"
        body_lines = []
        for row in rows[:MAX_ROWS]:
            body_lines.append("| " + " | ".join(row) + " |")
        return "\n".join([header, sep] + body_lines)

    # ------------------------------------------------------------------
    # Section execution
    # ------------------------------------------------------------------

    def _run_section(self, idx: int, section: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        title = str(section.get("title") or f"Bagian {idx + 1}")
        instruction = str(section.get("instruction") or "").strip()
        if not instruction:
            return idx, {"title": title, "error": GENERIC_SECTION_ERROR}
        try:
            db_result = self.database_agent.execute(instruction)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Section %d (%s) failed: %s", idx, title, exc)
            return idx, {
                "title": title,
                "instruction": instruction,
                "error": GENERIC_SECTION_ERROR,
            }

        if db_result.metadata.get("error") or str(db_result.output).startswith("Error:"):
            return idx, {
                "title": title,
                "instruction": instruction,
                "error": str(db_result.output)[:300],
            }

        columns, rows, parse_hint = self._parse_table(db_result.output)
        if not columns or not rows:
            error_msg = parse_hint or "No data available."
            return idx, {
                "title": title,
                "instruction": instruction,
                "error": error_msg,
            }

        return idx, {
            "title": title,
            "instruction": instruction,
            "columns": columns,
            "rows": rows[:MAX_ROWS],
            "row_count": len(rows),
        }

    # ------------------------------------------------------------------
    # Fallback & compile
    # ------------------------------------------------------------------

    def _fallback_report(self, plan: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
        title = plan.get("title") or "Laporan Operasional"
        period = plan.get("period") or ""
        lines = [f"# {title}"]
        if period:
            lines.append(f"_Periode: {period}_")
        lines.append("")
        for section in sections:
            lines.append(f"## {section.get('title', 'Bagian')}")
            if section.get("error"):
                lines.append(f"Catatan: {section.get('error')}")
                lines.append("")
                continue
            columns = section.get("columns") or []
            rows = section.get("rows") or []
            lines.append(self._table_to_markdown(columns, rows))
            lines.append("")
        content = "\n".join(lines).strip()
        filename = "report.md"
        return {
            "report": {
                "title": title,
                "period": period,
                "format": "markdown",
                "filename": filename,
                "content": content,
            }
        }

    @staticmethod
    def _attach_query(report_payload: dict[str, Any], question: str) -> dict[str, Any]:
        report = report_payload.get("report")
        if isinstance(report, dict):
            report.setdefault("query", question)
        return report_payload

    def _compile_report(self, question: str, plan: dict[str, Any], sections: list[dict[str, Any]]) -> dict[str, Any]:
        messages = self._build_compile_messages(question, plan, sections)
        response = self.llm.generate(messages=messages, config=GenerateConfig(temperature=0.2))
        raw = self._strip_json_fence(self._strip_think_tags(response.text))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Failed to parse report JSON, falling back.")
            return self._fallback_report(plan, sections)
        if not isinstance(payload, dict) or "report" not in payload:
            return self._fallback_report(plan, sections)
        return payload

    # ------------------------------------------------------------------
    # Execute (non-streaming)
    # ------------------------------------------------------------------

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        question = input_text.strip()
        if not question:
            return AgentResult(output="Error: Empty query.", metadata={"error": "empty query"})

        entity_context = self._fetch_entity_context()

        plan_messages = self._build_plan_messages(question, entity_context=entity_context)
        plan_response = self.llm.generate(messages=plan_messages, config=GenerateConfig(temperature=0))
        plan = self._parse_plan(plan_response.text)
        if not plan:
            return AgentResult(output="Error: Failed to create report plan.", metadata={"error": "plan"})

        plan_sections = plan.get("sections", [])[:MAX_SECTIONS]

        section_results: list[dict[str, Any]] = []
        for idx, section in enumerate(plan_sections):
            _, payload = self._run_section(idx, section)
            section_results.append(payload)

        report_payload = self._attach_query(
            self._compile_report(question, plan, section_results), question
        )
        return AgentResult(
            output=json.dumps(report_payload, ensure_ascii=False),
            metadata={
                "plan": plan,
                "sections": section_results,
            },
        )

    # ------------------------------------------------------------------
    # Execute (streaming with thinking events)
    # ------------------------------------------------------------------

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        question = input_text.strip()
        if not question:
            yield {"type": "content", "content": "Error: Empty query."}
            return

        yield {"type": "thinking", "content": "Mengambil konteks entity...\n"}
        entity_context = self._fetch_entity_context()

        yield {"type": "thinking", "content": "Menyusun rencana laporan...\n"}
        plan_messages = self._build_plan_messages(question, entity_context=entity_context)
        plan_response = self.llm.generate(messages=plan_messages, config=GenerateConfig(temperature=0))
        plan = self._parse_plan(plan_response.text)
        if not plan:
            yield {"type": "thinking", "content": f"Plan parse gagal. Raw: {plan_response.text[:300]}\n\n"}
            yield {"type": "content", "content": "Error: Failed to create report plan."}
            return

        plan_sections = plan.get("sections", [])[:MAX_SECTIONS]
        if not plan_sections:
            yield {"type": "content", "content": "Error: Laporan tidak memiliki bagian data."}
            return

        # Show plan summary in thinking
        section_titles = [s.get("title", "?") for s in plan_sections]
        yield {
            "type": "thinking",
            "content": (
                f"Rencana laporan: {plan.get('title', '-')}\n"
                f"Periode: {plan.get('period', '-')}\n"
                f"Sections ({len(plan_sections)}): {', '.join(section_titles)}\n\n"
            ),
        }

        section_results: list[dict[str, Any]] = []
        for idx, section in enumerate(plan_sections):
            title = str(section.get("title") or f"Bagian {idx + 1}")
            instruction = str(section.get("instruction") or "")
            yield {"type": "thinking", "content": f"[{idx+1}/{len(plan_sections)}] {title}\n  Instruksi: {instruction[:150]}\n"}
            _, payload = self._run_section(idx, section)
            section_results.append(payload)
            if payload.get("error"):
                yield {"type": "thinking", "content": f"  Gagal: {payload['error'][:200]}\n\n"}
            else:
                row_count = payload.get("row_count")
                cols = payload.get("columns", [])
                suffix = f"{row_count} baris, kolom: {', '.join(cols[:5])}" if row_count is not None else "selesai"
                yield {"type": "thinking", "content": f"  OK: {suffix}\n\n"}

        yield {"type": "thinking", "content": "Menyusun dokumen laporan...\n"}
        report_payload = self._attach_query(
            self._compile_report(question, plan, section_results), question
        )
        result = AgentResult(
            output=json.dumps(report_payload, ensure_ascii=False),
            metadata={
                "plan": plan,
                "sections": section_results,
            },
        )
        yield {"type": "_result", "data": result}
