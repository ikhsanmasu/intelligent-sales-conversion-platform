from collections.abc import Generator

import google.generativeai as genai

from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig, LLMResponse


class GoogleProvider(BaseLLM):
    def __init__(self, api_key: str, model: str):
        genai.configure(api_key=api_key)
        self._model = model

    def _split_messages(self, messages: list[dict]) -> tuple[str | None, list[dict]]:
        system_parts: list[str] = []
        history: list[dict] = []

        for message in messages:
            role = message.get("role")
            content = message.get("content", "")
            if role == "system":
                if content:
                    system_parts.append(str(content))
                continue
            if role == "assistant":
                history.append({"role": "model", "parts": [str(content)]})
            else:
                history.append({"role": "user", "parts": [str(content)]})

        system_instruction = "\n\n".join(system_parts) if system_parts else None
        return system_instruction, history

    def _build_config(self, config: GenerateConfig) -> genai.types.GenerationConfig:
        params: dict = {
            "temperature": config.temperature,
            "top_p": config.top_p,
        }
        if config.max_tokens is not None:
            params["max_output_tokens"] = config.max_tokens
        if config.stop is not None:
            params["stop_sequences"] = config.stop
        return genai.types.GenerationConfig(**params)

    def generate(self, messages: list[dict], config: GenerateConfig | None = None) -> LLMResponse:
        config = config or GenerateConfig()
        system_instruction, history = self._split_messages(messages)
        model = genai.GenerativeModel(self._model, system_instruction=system_instruction)
        response = model.generate_content(
            history or "",
            generation_config=self._build_config(config),
        )
        text = getattr(response, "text", "") or ""
        return LLMResponse(text=text, usage={})

    def generate_stream(
        self,
        messages: list[dict],
        config: GenerateConfig | None = None,
    ) -> Generator[str, None, None]:
        config = config or GenerateConfig()
        system_instruction, history = self._split_messages(messages)
        model = genai.GenerativeModel(self._model, system_instruction=system_instruction)
        stream = model.generate_content(
            history or "",
            generation_config=self._build_config(config),
            stream=True,
        )
        for chunk in stream:
            text = getattr(chunk, "text", "")
            if text:
                yield text
