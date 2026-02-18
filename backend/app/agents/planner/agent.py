import re
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.core.config import settings
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_config, resolve_prompt


class PlannerAgent(BaseAgent):
    """Sales agent — full LLM driven, no hardcoded stage logic."""

    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _strip_think_tags(text: str) -> str:
        return re.sub(r"<think>.*?</think>", "", text or "", flags=re.DOTALL).strip()

    @staticmethod
    def _normalize_usage(raw: dict | None, prompt: str = "", output: str = "") -> dict:
        raw = raw or {}
        inp = int(raw.get("prompt_tokens") or raw.get("input_tokens") or max(1, len(prompt) // 4))
        out = int(raw.get("completion_tokens") or raw.get("output_tokens") or max(1, len(output) // 4))
        return {
            "input_tokens": inp,
            "output_tokens": out,
            "prompt_tokens": inp,
            "completion_tokens": out,
            "total_tokens": inp + out,
        }

    @staticmethod
    def _resolve_llm_identity() -> tuple[str, str]:
        provider, model = settings.CHATBOT_DEFAULT_LLM, settings.CHATBOT_DEFAULT_MODEL
        try:
            provider = (
                resolve_config("llm_planner", "provider")
                or resolve_config("llm", "default_provider")
                or provider
            )
            model = (
                resolve_config("llm_planner", "model")
                or resolve_config("llm", "default_model")
                or model
            )
        except Exception:
            pass
        return str(provider), str(model)

    # ── Prompt & Message Building ──────────────────────────────────────────────

    @staticmethod
    def _safe_render_template(template: str, variables: dict[str, str]) -> str:
        rendered = str(template or "")
        for key, value in variables.items():
            rendered = rendered.replace(f"{{{key}}}", str(value))
        return rendered

    def _build_system_prompt(self, memory_summary: str | None) -> str:
        product_knowledge = str(resolve_prompt("product_knowledge") or "").strip()
        raw = str(resolve_prompt("sales_system") or "").strip()
        system = self._safe_render_template(raw, {"product_knowledge": product_knowledge}).strip()

        if memory_summary:
            system += f"\n\n## Konteks Sesi Sebelumnya\n{str(memory_summary)[:700]}"

        return system

    _MAX_HISTORY = 15

    @staticmethod
    def _build_messages(
        input_text: str,
        history: list[dict] | None,
        system_prompt: str,
    ) -> list[dict]:
        """Last 15 messages passed to LLM. Older context handled by memory_summary in system prompt."""
        normalized = [
            {"role": m["role"], "content": str(m.get("content", ""))}
            for m in (history or [])
            if m.get("role") in {"user", "assistant"} and str(m.get("content", "")).strip()
        ]
        return [
            {"role": "system", "content": system_prompt},
            *normalized[-PlannerAgent._MAX_HISTORY:],
            {"role": "user", "content": input_text},
        ]

    @staticmethod
    def _llm_config() -> GenerateConfig:
        return GenerateConfig(temperature=0.4, max_tokens=300)

    @staticmethod
    def _chunk_text(text: str, chunk_size: int = 70) -> list[str]:
        return [text[i: i + chunk_size] for i in range(0, len(text), chunk_size)] if text else []

    # ── Execution ──────────────────────────────────────────────────────────────

    def execute(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> AgentResult:
        context = context or {}
        system = self._build_system_prompt(context.get("memory_summary"))
        messages = self._build_messages(input_text, history, system)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)

        try:
            response = self.llm.generate(messages=messages, config=self._llm_config())
            output = self._strip_think_tags(response.text).strip()
            usage = self._normalize_usage(response.usage, prompt=prompt_text, output=output)
        except Exception:
            output = "Makasih udah cerita. Biar aku bantu lebih tepat, boleh aku tahu kondisi kulitmu sekarang?"
            usage = self._normalize_usage({}, prompt=prompt_text, output=output)

        provider, model = self._resolve_llm_identity()
        return AgentResult(
            output=output,
            metadata={
                "agent": "sales",
                "model": {"provider": provider, "name": model},
                "usage": usage,
            },
        )

    def execute_stream(
        self,
        input_text: str,
        context: dict | None = None,
        history: list[dict] | None = None,
    ) -> Generator[dict, None, None]:
        context = context or {}
        system = self._build_system_prompt(context.get("memory_summary"))
        messages = self._build_messages(input_text, history, system)
        prompt_text = "\n".join(str(m.get("content", "")) for m in messages)

        try:
            response = self.llm.generate(messages=messages, config=self._llm_config())
            output = self._strip_think_tags(response.text).strip()
            usage = self._normalize_usage(response.usage, prompt=prompt_text, output=output)
        except Exception:
            output = "Maaf, bisa cerita ulang sedikit masalah kulitmu biar aku bantu lebih tepat?"
            usage = self._normalize_usage({}, prompt=prompt_text, output=output)

        for chunk in self._chunk_text(output):
            yield {"type": "content", "content": chunk}

        provider, model = self._resolve_llm_identity()
        yield {
            "type": "meta",
            "metadata": {
                "agent": "sales",
                "model": {"provider": provider, "name": model},
                "usage": usage,
            },
        }
