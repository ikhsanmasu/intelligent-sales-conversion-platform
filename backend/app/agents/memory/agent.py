import json
import logging
import re
from collections.abc import Generator
from typing import Any

from app.agents.base import AgentResult, BaseAgent
from app.agents.memory.store import clear_memory, get_memory_summary, upsert_memory_summary
from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig
from app.modules.admin.service import resolve_prompt

logger = logging.getLogger(__name__)

MAX_MESSAGES = 24


class MemoryAgent(BaseAgent):
    def __init__(self, llm: BaseLLM):
        super().__init__(llm)

    @staticmethod
    def _strip_json_fence(raw_text: str) -> str:
        raw = raw_text.strip()
        if raw.startswith("```"):
            raw = re.sub(r"^```(?:json)?\s*", "", raw)
            raw = re.sub(r"\s*```$", "", raw)
        return raw

    def _summarize_messages(self, messages: list[dict[str, str]]) -> str:
        payload = json.dumps(messages, ensure_ascii=True)
        prompt_messages = [
            {"role": "system", "content": resolve_prompt("memory_summarize_system")},
            {
                "role": "user",
                "content": resolve_prompt("memory_summarize_user").format(messages=payload),
            },
        ]
        response = self.llm.generate(messages=prompt_messages, config=GenerateConfig(temperature=0.2))
        return response.text.strip()

    def _handle_get(self, payload: dict[str, Any]) -> AgentResult:
        user_id = str(payload.get("user_id") or "").strip()
        agent = str(payload.get("agent") or "planner").strip()
        conversation_id = payload.get("conversation_id")
        if not user_id:
            return AgentResult(output="Error: user_id is required.", metadata={"error": "user_id"})

        summary = get_memory_summary(user_id=user_id, agent=agent, conversation_id=conversation_id)
        if not summary:
            return AgentResult(output="(no memory)", metadata={"count": 0})
        return AgentResult(output=summary, metadata={"count": 1})

    def _handle_clear(self, payload: dict[str, Any]) -> AgentResult:
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            return AgentResult(output="Error: user_id is required.", metadata={"error": "user_id"})
        agent = payload.get("agent")
        conversation_id = payload.get("conversation_id")
        deleted = clear_memory(user_id=user_id, agent=agent, conversation_id=conversation_id)
        return AgentResult(output=f"Cleared {deleted} memory entries.", metadata={"count": deleted})

    def _handle_summarize(self, payload: dict[str, Any]) -> AgentResult:
        user_id = str(payload.get("user_id") or "").strip()
        if not user_id:
            return AgentResult(output="Error: user_id is required.", metadata={"error": "user_id"})
        agent = str(payload.get("agent") or "planner").strip()
        conversation_id = payload.get("conversation_id")
        messages = payload.get("messages")

        if not isinstance(messages, list) or not messages:
            return AgentResult(output="Error: messages are required.", metadata={"error": "messages"})

        trimmed = []
        for item in messages[-MAX_MESSAGES:]:
            if not isinstance(item, dict):
                continue
            role = str(item.get("role") or "").strip()
            content = str(item.get("content") or "").strip()
            if role and content:
                trimmed.append({"role": role, "content": content})

        if not trimmed:
            return AgentResult(output="Error: messages are empty.", metadata={"error": "messages"})

        summary = self._summarize_messages(trimmed)
        upsert_memory_summary(
            user_id=user_id,
            summary=summary,
            agent=agent,
            conversation_id=conversation_id,
        )
        return AgentResult(output=summary, metadata={"count": 1})

    def execute(self, input_text: str, context: dict | None = None) -> AgentResult:
        raw = self._strip_json_fence(input_text)
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            return AgentResult(output=f"Error: Invalid JSON ({exc}).", metadata={"error": "json"})

        if not isinstance(payload, dict):
            return AgentResult(output="Error: Payload must be a JSON object.", metadata={"error": "payload"})

        action = str(payload.get("action") or "get").strip().lower()
        if action == "get":
            return self._handle_get(payload)
        if action == "summarize":
            return self._handle_summarize(payload)
        if action == "clear":
            return self._handle_clear(payload)
        return AgentResult(output="Error: Unsupported action.", metadata={"error": "action"})

    def execute_stream(self, input_text: str, context: dict | None = None) -> Generator[dict, None, None]:
        yield {"type": "thinking", "content": "Memproses memori...\n"}
        result = self.execute(input_text, context=context)
        yield {"type": "_result", "data": result}
