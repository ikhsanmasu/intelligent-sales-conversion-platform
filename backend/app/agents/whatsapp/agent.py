import re
from collections.abc import Generator

from app.agents.base import AgentResult, BaseAgent
from app.channels.media import (
    WHATSAPP_SPLIT_MARKER,
    format_whatsapp_reply_text,
    split_whatsapp_bubbles,
)
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

_DEFAULT_WHATSAPP_POLISH_SYSTEM_PROMPT = (
    "Kamu adalah formatter khusus WhatsApp untuk sales chat.\n"
    "Tugasmu memoles draft jawaban agar natural, singkat, dan enak dibaca.\n\n"
    "Aturan wajib:\n"
    "- Pertahankan fakta inti, jangan menambah klaim baru.\n"
    "- Gaya santai, empatik, tidak kaku.\n"
    "- Hilangkan markdown teknis / format yang tidak cocok untuk WhatsApp.\n"
    "- Jika terlalu panjang, pecah jadi beberapa bubble.\n\n"
    "Output rules:\n"
    "- Output plain text saja.\n"
    "- Jika butuh lebih dari 1 bubble, pisahkan bubble dengan token persis: {split_marker}\n"
    "- Jika 1 bubble saja, jangan pakai token split.\n"
    "- Maksimal 4 bubble.\n"
    "- Tiap bubble ideal 1-3 kalimat dan <= 280 karakter.\n"
    "- Jangan output JSON. Jangan gunakan code fence."
)


class WhatsAppPolisherAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    @staticmethod
    def _llm_config() -> GenerateConfig:
        return GenerateConfig(temperature=0.2, max_tokens=420)

    @staticmethod
    def _strip_code_fence(text: str) -> str:
        raw = str(text or "").strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:[a-zA-Z0-9_-]+)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return raw.strip()

    def _system_prompt(self) -> str:
        prompt = str(resolve_prompt("whatsapp_polish_system") or "").strip()
        if not prompt:
            prompt = _DEFAULT_WHATSAPP_POLISH_SYSTEM_PROMPT
        return prompt.replace("{split_marker}", WHATSAPP_SPLIT_MARKER)

    def _build_messages(self, draft: str, user_text: str, stage: str) -> list[dict]:
        safe_user = str(user_text or "").strip()
        safe_stage = str(stage or "").strip().lower() or "general"
        return [
            {"role": "system", "content": self._system_prompt()},
            {
                "role": "user",
                "content": (
                    f"Pesan user:\n{safe_user}\n\n"
                    f"Tahap percakapan:\n{safe_stage}\n\n"
                    f"Draft balasan:\n{draft}\n\n"
                    "Tulis versi final WhatsApp sekarang."
                ),
            },
        ]

    @staticmethod
    def _fallback_bubbles(draft: str) -> list[str]:
        return split_whatsapp_bubbles(format_whatsapp_reply_text(draft))

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        context = context or {}
        draft = format_whatsapp_reply_text(input_text)
        if not draft:
            return AgentResult(output="", metadata={"bubbles": [], "used_llm": False})

        user_text = str(context.get("user_text") or "")
        stage = str(context.get("stage") or "")

        try:
            response = self.llm.generate(
                messages=self._build_messages(draft=draft, user_text=user_text, stage=stage),
                config=self._llm_config(),
            )
            polished = self._strip_code_fence(response.text)
            polished = format_whatsapp_reply_text(polished)
            bubbles = split_whatsapp_bubbles(polished)
            if not bubbles:
                raise ValueError("empty_whatsapp_polisher_output")

            return AgentResult(
                output=WHATSAPP_SPLIT_MARKER.join(bubbles),
                metadata={
                    "bubbles": bubbles,
                    "used_llm": True,
                    "usage": response.usage if isinstance(response.usage, dict) else {},
                },
            )
        except Exception:
            bubbles = self._fallback_bubbles(draft)
            return AgentResult(
                output=WHATSAPP_SPLIT_MARKER.join(bubbles),
                metadata={"bubbles": bubbles, "used_llm": False},
            )

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        result = self.execute(input_text=input_text, context=context)
        for bubble in result.metadata.get("bubbles", []):
            yield {"type": "content", "content": bubble}
        yield {"type": "meta", "metadata": result.metadata}
