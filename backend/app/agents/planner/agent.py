import json
import logging
import re
from collections.abc import Generator

from sqlmodel import text

from app.agents.alert.agent import AlertAgent
from app.agents.base import AgentResult, BaseAgent
from app.agents.browser.agent import BrowserAgent
from app.agents.chart.agent import ChartAgent
from app.agents.compare.agent import CompareAgent
from app.agents.database.agent import DatabaseAgent
from app.agents.report.agent import ReportAgent
from app.agents.planner.schemas import (
    ALERT_ROUTE,
    BROWSER_ROUTE,
    CHART_ROUTE,
    COMPARE_ROUTE,
    DATABASE_ROUTE,
    GENERAL_ROUTE,
    REPORT_ROUTE,
    TIMESERIES_ROUTE,
    VECTOR_ROUTE,
    RoutingDecision,
)
from app.agents.timeseries.agent import TimeSeriesAgent
from app.agents.vector.agent import VectorAgent
from app.agents.planner.streaming import parse_think_tags
from app.core.database import clickhouse_engine
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_config, resolve_prompt

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Domain cheatsheet — condensed reference injected into routing & command prompts
# so the planner knows what data exists without needing the full SQL schema.
# ---------------------------------------------------------------------------
DOMAIN_CONTEXT = (
    "DATA YANG TERSEDIA DI PLATFORM:\n"
    "Hierarchy: Site (lokasi tambak) → Pond (kolam) → Cultivation (siklus budidaya)\n\n"
    "Metrik KPI:\n"
    "- ABW (gram), ADG (g/hari), SR (%), FCR, DOC (hari), biomassa (kg)\n"
    "- size (ekor/kg), produktivitas (ton/ha), populasi (ekor)\n\n"
    "Kualitas air:\n"
    "- DO (mg/L), pH, salinitas (ppt), suhu (°C), NH4/ammonium (mg/L)\n"
    "- NO2/nitrit (mg/L), alkalinitas, kecerahan\n\n"
    "Data tersedia:\n"
    "- Tebar benur (tanggal, jumlah, asal benur)\n"
    "- Sampling udang harian (ABW, ADG, SR, biomassa)\n"
    "- Pakan harian (jumlah pakan, FCR, merek pakan)\n"
    "- Panen (parsial & total — biomassa, size, ABW, SR, FCR, produktivitas)\n"
    "- Kualitas air harian (fisika, kimia, biologi)\n"
    "- Treatment & obat, persiapan kolam, transfer udang\n"
    "- Alert/alarm, energi, harga udang pasar\n\n"
    "Report views (data sudah di-aggregate, lebih cepat):\n"
    "- site_pond_latest_report — KPI terkini per kolam\n"
    "- budidaya_report — ringkasan KPI per siklus\n"
    "- budidaya_panen_report_v2 — detail panen\n"
    "- cultivation_water_report — kualitas air harian konsolidasi\n"
)


class PlannerAgent(BaseAgent):
    def __init__(
        self,
        llm: BaseLLM,
        database_agent: DatabaseAgent,
        vector_agent: VectorAgent,
        browser_agent: BrowserAgent,
        chart_agent: ChartAgent,
        report_agent: ReportAgent,
        timeseries_agent: TimeSeriesAgent | None = None,
        compare_agent: CompareAgent | None = None,
        alert_agent: AlertAgent | None = None,
    ):
        super().__init__(llm)
        self.database_agent = database_agent
        self.vector_agent = vector_agent
        self.browser_agent = browser_agent
        self.chart_agent = chart_agent
        self.report_agent = report_agent
        self.timeseries_agent = timeseries_agent
        self.compare_agent = compare_agent
        self.alert_agent = alert_agent

    # ------------------------------------------------------------------
    # Entity resolution — fetch real site names from ClickHouse so the
    # routing LLM can map user input to exact names.
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
                "Contoh: user bilang 'teluk tomini' → gunakan 'ARONA TELUK TOMINI'.\n"
                "Contoh: user bilang 'suma' → gunakan 'SUMA MARINA'.\n"
                "SELALU gunakan nama site PERSIS dari daftar di atas di routed_input."
            )
        except Exception as exc:
            logger.warning("Failed to fetch entity context: %s", exc)
            return ""

    def _build_db_plan_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("db_plan_system")},
            {"role": "user", "content": resolve_prompt("db_plan_user").format(question=user_message)},
        ]

    def _build_routing_messages(self, user_message: str, entity_context: str = "") -> list[dict[str, str]]:
        system_content = resolve_prompt("routing_system")
        if entity_context:
            system_content += "\n\n" + entity_context
        system_content += "\n\n" + DOMAIN_CONTEXT
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": resolve_prompt("routing_user").format(message=user_message)},
        ]

    def _build_general_messages(
        self,
        user_message: str,
        history: list[dict] | None = None,
        memory_summary: str | None = None,
    ) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = [
            {"role": "system", "content": resolve_prompt("general_system")},
        ]
        if memory_summary:
            messages.append(
                {
                    "role": "system",
                    "content": f"Konteks pengguna (ringkas):\n{memory_summary}",
                }
            )
        if history:
            messages.extend(history)
        messages.append({"role": "user", "content": user_message})
        return messages

    def _build_synthesis_messages(self, question: str, database_output: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("synthesis_system")},
            {"role": "user", "content": resolve_prompt("synthesis_user").format(
                question=question,
                results=database_output,
            )},
        ]

    def _build_db_command_messages(self, user_message: str, entity_context: str = "") -> list[dict[str, str]]:
        system_content = resolve_prompt("db_command_system")
        if entity_context:
            system_content += "\n\n" + entity_context
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": resolve_prompt("db_command_user").format(message=user_message)},
        ]

    def _build_vector_command_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("vector_command_system")},
            {"role": "user", "content": resolve_prompt("vector_command_user").format(message=user_message)},
        ]

    def _build_ts_command_messages(self, user_message: str) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("ts_command_system")},
            {"role": "user", "content": resolve_prompt("ts_command_user").format(message=user_message)},
        ]

    def _build_db_reflection_messages(
        self,
        question: str,
        plan: str,
        instruction: str,
        error: str,
    ) -> list[dict[str, str]]:
        return [
            {"role": "system", "content": resolve_prompt("db_reflection_system")},
            {
                "role": "user",
                "content": resolve_prompt("db_reflection_user").format(
                    question=question,
                    plan=plan or "-",
                    instruction=instruction,
                    error=error,
                ),
            },
        ]

    @staticmethod
    def _disabled_agent_message(agent: str) -> str:
        return (
            f"Agent '{agent}' sedang dinonaktifkan di konfigurasi. "
            "Aktifkan dulu di halaman Config untuk menggunakan fitur ini."
        )

    @staticmethod
    def _is_truthy(value: str) -> bool:
        return value.strip().lower() not in {"0", "false", "no", "off", "disabled"}

    def _is_agent_enabled(self, agent: str) -> bool:
        if agent in {GENERAL_ROUTE}:
            return True
        try:
            raw = resolve_config("agents", agent)
        except Exception:
            return True
        if raw is None or raw == "":
            return True
        return self._is_truthy(str(raw))

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

    def _parse_json(self, raw_text: str) -> dict | None:
        raw = self._strip_json_fence(raw_text)
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            return None
        return None

    @staticmethod
    def _format_plan_summary(plan: dict | None) -> str:
        if not plan:
            return ""
        parts: list[str] = []
        steps = plan.get("steps") if isinstance(plan.get("steps"), list) else None
        tables = plan.get("tables") if isinstance(plan.get("tables"), list) else None
        filters = plan.get("filters") if isinstance(plan.get("filters"), list) else None
        time_range = plan.get("time_range")
        risk = plan.get("risk")
        notes = plan.get("notes")

        if steps:
            parts.append("Langkah: " + "; ".join(str(s) for s in steps))
        if tables:
            parts.append("Tabel: " + ", ".join(str(t) for t in tables))
        if filters:
            parts.append("Filter: " + "; ".join(str(f) for f in filters))
        if time_range:
            parts.append(f"Rentang waktu: {time_range}")
        if risk:
            parts.append(f"Risiko: {risk}")
        if notes:
            parts.append(f"Catatan: {notes}")
        return "\n".join(parts)

    @staticmethod
    def _should_reflect(db_result: AgentResult) -> bool:
        if db_result.metadata.get("error"):
            return True
        output = db_result.output or ""
        return isinstance(output, str) and output.strip().startswith("Error:")

    def _route_message(self, user_message: str, entity_context: str = "") -> RoutingDecision:
        messages = self._build_routing_messages(user_message, entity_context=entity_context)
        config = GenerateConfig(temperature=0)
        response = self.llm.generate(messages=messages, config=config)

        raw = self._strip_json_fence(response.text)

        try:
            parsed = json.loads(raw)
            return RoutingDecision.from_payload(parsed, fallback_input=user_message)
        except (json.JSONDecodeError, KeyError) as e:
            logger.warning("Failed to parse route decision, defaulting to general: %s", e)
            return RoutingDecision(
                target_agent=GENERAL_ROUTE,
                reasoning="Failed to parse routing decision, defaulting to general.",
                routed_input=user_message,
            )

    def execute(self, input_text: str, context: dict | None = None, history: list[dict] | None = None) -> AgentResult:
        entity_context = self._fetch_entity_context()
        decision = self._route_message(input_text, entity_context=entity_context)
        if not self._is_agent_enabled(decision.target_agent):
            return AgentResult(
                output=self._disabled_agent_message(decision.target_agent),
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    "disabled": True,
                },
            )

        if decision.target_agent == DATABASE_ROUTE:
            plan_summary = ""
            plan_usage = None
            try:
                plan_messages = self._build_db_plan_messages(decision.routed_input)
                plan_config = GenerateConfig(temperature=0)
                plan_response = self.llm.generate(messages=plan_messages, config=plan_config)
                plan_usage = plan_response.usage
                plan_payload = self._parse_json(plan_response.text)
                plan_summary = self._format_plan_summary(plan_payload)
                if not plan_summary:
                    plan_summary = self._strip_think_tags(plan_response.text)
            except Exception as exc:
                logger.warning("Failed to build plan: %s", exc)

            command_input = decision.routed_input
            if plan_summary:
                command_input = f"{decision.routed_input}\n\nRencana:\n{plan_summary}"
            command_messages = self._build_db_command_messages(command_input, entity_context=entity_context)
            command_config = GenerateConfig(temperature=0)
            command_response = self.llm.generate(messages=command_messages, config=command_config)
            db_instruction = self._strip_think_tags(command_response.text)

            db_result = self.database_agent.execute(db_instruction)

            reflection_usage = None
            if self._should_reflect(db_result):
                error_msg = db_result.metadata.get("error") or db_result.output
                reflection_messages = self._build_db_reflection_messages(
                    question=input_text,
                    plan=plan_summary,
                    instruction=db_instruction,
                    error=str(error_msg),
                )
                reflection_config = GenerateConfig(temperature=0)
                reflection_response = self.llm.generate(
                    messages=reflection_messages,
                    config=reflection_config,
                )
                reflection_usage = reflection_response.usage
                reflected_instruction = self._strip_think_tags(reflection_response.text)
                if reflected_instruction and reflected_instruction != db_instruction:
                    db_instruction = reflected_instruction
                    db_result = self.database_agent.execute(db_instruction)

            # Synthesize the result into natural language
            messages = self._build_synthesis_messages(
                question=input_text,
                database_output=db_result.output,
            )
            response = self.llm.generate(messages=messages)
            return AgentResult(
                output=response.text,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    "plan": plan_summary,
                    "plan_usage": plan_usage,
                    "db_instruction": db_instruction,
                    "instruction_usage": command_response.usage,
                    "reflection_usage": reflection_usage,
                    **db_result.metadata,
                    "usage": response.usage,
                },
            )

        if decision.target_agent == VECTOR_ROUTE:
            command_messages = self._build_vector_command_messages(decision.routed_input)
            command_config = GenerateConfig(temperature=0)
            command_response = self.llm.generate(messages=command_messages, config=command_config)
            payload = self._parse_json(command_response.text)
            if not payload or payload.get("error"):
                error_msg = payload.get("error") if payload else "Invalid vector instruction."
                return AgentResult(
                    output=f"Error: {error_msg}",
                    metadata={
                        "agent": decision.target_agent,
                        "routing_reasoning": decision.reasoning,
                        "vector_error": error_msg,
                    },
                )

            instruction = json.dumps(payload, ensure_ascii=True)
            vector_result = self.vector_agent.execute(instruction)
            return AgentResult(
                output=vector_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    "vector_instruction": instruction,
                    **vector_result.metadata,
                },
            )

        if decision.target_agent == BROWSER_ROUTE:
            browser_result = self.browser_agent.execute(decision.routed_input, context=context)
            return AgentResult(
                output=browser_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    **browser_result.metadata,
                },
            )

        if decision.target_agent == CHART_ROUTE:
            chart_result = self.chart_agent.execute(decision.routed_input, context=context)
            return AgentResult(
                output=chart_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    **chart_result.metadata,
                },
            )

        if decision.target_agent == REPORT_ROUTE:
            report_result = self.report_agent.execute(decision.routed_input, context=context)
            return AgentResult(
                output=report_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    **report_result.metadata,
                },
            )

        if decision.target_agent == TIMESERIES_ROUTE:
            if self.timeseries_agent is None:
                return AgentResult(
                    output="Error: TimeSeries agent is not configured.",
                    metadata={"agent": decision.target_agent, "error": "not configured"},
                )
            ts_result = self.timeseries_agent.execute(decision.routed_input, context=context)
            return AgentResult(
                output=ts_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    **ts_result.metadata,
                },
            )

        if decision.target_agent == COMPARE_ROUTE:
            if self.compare_agent is None:
                return AgentResult(
                    output="Error: Compare agent is not configured.",
                    metadata={"agent": decision.target_agent, "error": "not configured"},
                )
            cmp_result = self.compare_agent.execute(decision.routed_input, context=context)
            return AgentResult(
                output=cmp_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    **cmp_result.metadata,
                },
            )

        if decision.target_agent == ALERT_ROUTE:
            if self.alert_agent is None:
                return AgentResult(
                    output="Error: Alert agent is not configured.",
                    metadata={"agent": decision.target_agent, "error": "not configured"},
                )
            alert_result = self.alert_agent.execute(decision.routed_input, context=context)
            return AgentResult(
                output=alert_result.output,
                metadata={
                    "agent": decision.target_agent,
                    "routing_reasoning": decision.reasoning,
                    **alert_result.metadata,
                },
            )

        memory_summary = None
        if context:
            memory_summary = context.get("memory_summary")
        messages = self._build_general_messages(
            input_text,
            history=history,
            memory_summary=memory_summary,
        )
        response = self.llm.generate(messages=messages)
        return AgentResult(
            output=response.text,
            metadata={
                "agent": decision.target_agent,
                "routing_reasoning": decision.reasoning,
                "usage": response.usage,
            },
        )

    def execute_stream(self, input_text: str, context: dict | None = None, history: list[dict] | None = None) -> Generator[dict, None, None]:
        entity_context = self._fetch_entity_context()
        decision = self._route_message(input_text, entity_context=entity_context)

        # Emit routing decision as thinking
        yield {
            "type": "thinking",
            "content": (
                "Routing permintaan\n"
                f"Target: {decision.target_agent}\n"
                f"Alasan: {decision.reasoning}\n\n"
            ),
        }
        if not self._is_agent_enabled(decision.target_agent):
            yield {"type": "content", "content": self._disabled_agent_message(decision.target_agent)}
            return

        if decision.target_agent == DATABASE_ROUTE:
            plan_summary = ""
            yield {"type": "thinking", "content": "Menyusun rencana query...\n"}
            try:
                plan_messages = self._build_db_plan_messages(decision.routed_input)
                plan_config = GenerateConfig(temperature=0)
                plan_response = self.llm.generate(messages=plan_messages, config=plan_config)
                plan_payload = self._parse_json(plan_response.text)
                plan_summary = self._format_plan_summary(plan_payload)
                if not plan_summary:
                    plan_summary = self._strip_think_tags(plan_response.text)
            except Exception as exc:
                logger.warning("Failed to build plan: %s", exc)

            if plan_summary:
                yield {
                    "type": "thinking",
                    "content": f"Rencana query\n{plan_summary}\n\n",
                }

            command_input = decision.routed_input
            if plan_summary:
                command_input = f"{decision.routed_input}\n\nRencana:\n{plan_summary}"
            command_messages = self._build_db_command_messages(command_input, entity_context=entity_context)
            command_config = GenerateConfig(temperature=0)
            command_response = self.llm.generate(messages=command_messages, config=command_config)
            db_instruction = self._strip_think_tags(command_response.text)

            yield {
                "type": "thinking",
                "content": (
                    "Instruksi ke Database Agent\n"
                    f"Instruksi: {db_instruction}\n\n"
                ),
            }

            # Stream step-by-step thinking from DatabaseAgent
            db_result = None
            for event in self.database_agent.execute_stream(db_instruction):
                if event.get("type") == "_result":
                    db_result = event["data"]
                else:
                    yield event

            if db_result is None:
                yield {"type": "content", "content": "Error: Database agent returned no result."}
                return

            if self._should_reflect(db_result):
                error_msg = db_result.metadata.get("error") or db_result.output
                yield {"type": "thinking", "content": "Refleksi selektif: memperbaiki instruksi...\n"}
                reflection_messages = self._build_db_reflection_messages(
                    question=input_text,
                    plan=plan_summary,
                    instruction=db_instruction,
                    error=str(error_msg),
                )
                reflection_config = GenerateConfig(temperature=0)
                reflection_response = self.llm.generate(
                    messages=reflection_messages,
                    config=reflection_config,
                )
                reflected_instruction = self._strip_think_tags(reflection_response.text)
                if reflected_instruction and reflected_instruction != db_instruction:
                    db_instruction = reflected_instruction
                    yield {
                        "type": "thinking",
                        "content": f"Instruksi hasil refleksi: {db_instruction}\n\n",
                    }

                    db_result = None
                    for event in self.database_agent.execute_stream(db_instruction):
                        if event.get("type") == "_result":
                            db_result = event["data"]
                        else:
                            yield event

                    if db_result is None:
                        yield {"type": "content", "content": "Error: Database agent returned no result."}
                        return

            yield {"type": "thinking", "content": "Menyusun jawaban akhir...\n"}

            # Stream synthesis
            messages = self._build_synthesis_messages(
                question=input_text,
                database_output=db_result.output,
            )
            chunks = self.llm.generate_stream(messages=messages)
            yield from parse_think_tags(chunks)

            return

        if decision.target_agent == VECTOR_ROUTE:
            yield {"type": "thinking", "content": "Menyusun instruksi vector...\n"}
            command_messages = self._build_vector_command_messages(decision.routed_input)
            command_config = GenerateConfig(temperature=0)
            command_response = self.llm.generate(messages=command_messages, config=command_config)
            payload = self._parse_json(command_response.text)
            if not payload or payload.get("error"):
                error_msg = payload.get("error") if payload else "Invalid vector instruction."
                yield {"type": "content", "content": f"Error: {error_msg}"}
                return

            instruction = json.dumps(payload, ensure_ascii=True)
            yield {"type": "thinking", "content": f"Instruksi Vector Agent: {instruction}\n\n"}

            vector_result = None
            for event in self.vector_agent.execute_stream(instruction):
                if event.get("type") == "_result":
                    vector_result = event["data"]
                else:
                    yield event

            if vector_result is None:
                yield {"type": "content", "content": "Error: Vector agent returned no result."}
                return

            yield {"type": "content", "content": vector_result.output}
            return

        if decision.target_agent == BROWSER_ROUTE:
            yield {"type": "thinking", "content": "Menelusuri sumber internet...\n"}
            browser_result = None
            for event in self.browser_agent.execute_stream(decision.routed_input, context=context):
                if event.get("type") == "_result":
                    browser_result = event["data"]
                else:
                    yield event

            if browser_result is None:
                yield {"type": "content", "content": "Error: Browser agent returned no result."}
                return

            yield {"type": "content", "content": browser_result.output}
            return

        if decision.target_agent == CHART_ROUTE:
            yield {"type": "thinking", "content": "Menyiapkan chart...\n"}
            chart_result = None
            for event in self.chart_agent.execute_stream(decision.routed_input, context=context):
                if event.get("type") == "_result":
                    chart_result = event["data"]
                else:
                    yield event

            if chart_result is None:
                yield {"type": "content", "content": "Error: Chart agent returned no result."}
                return

            yield {"type": "content", "content": chart_result.output}
            return

        if decision.target_agent == REPORT_ROUTE:
            yield {"type": "thinking", "content": "Menyusun laporan...\n"}
            report_result = None
            for event in self.report_agent.execute_stream(decision.routed_input, context=context):
                if event.get("type") == "_result":
                    report_result = event["data"]
                else:
                    yield event

            if report_result is None:
                yield {"type": "content", "content": "Error: Report agent returned no result."}
                return

            yield {"type": "content", "content": report_result.output}
            return

        if decision.target_agent == TIMESERIES_ROUTE:
            if self.timeseries_agent is None:
                yield {"type": "content", "content": "Error: TimeSeries agent is not configured."}
                return

            yield {"type": "thinking", "content": "Memulai analisis time-series...\n"}
            for event in self.timeseries_agent.execute_stream(decision.routed_input, context=context):
                if event.get("type") == "_result":
                    pass
                else:
                    yield event
            return

        if decision.target_agent == COMPARE_ROUTE:
            if self.compare_agent is None:
                yield {"type": "content", "content": "Error: Compare agent is not configured."}
                return

            yield {"type": "thinking", "content": "Memulai analisis perbandingan...\n"}
            for event in self.compare_agent.execute_stream(decision.routed_input, context=context):
                if event.get("type") == "_result":
                    pass
                else:
                    yield event
            return

        if decision.target_agent == ALERT_ROUTE:
            if self.alert_agent is None:
                yield {"type": "content", "content": "Error: Alert agent is not configured."}
                return

            yield {"type": "thinking", "content": "Memeriksa alert dan threshold...\n"}
            for event in self.alert_agent.execute_stream(decision.routed_input, context=context):
                if event.get("type") == "_result":
                    pass
                else:
                    yield event
            return

        memory_summary = None
        if context:
            memory_summary = context.get("memory_summary")
        messages = self._build_general_messages(
            input_text,
            history=history,
            memory_summary=memory_summary,
        )
        chunks = self.llm.generate_stream(messages=messages)
        yield from parse_think_tags(chunks)
