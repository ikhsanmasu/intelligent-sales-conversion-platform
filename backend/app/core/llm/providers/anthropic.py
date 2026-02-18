from collections.abc import Generator

from anthropic import Anthropic

from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig, LLMResponse


class AnthropicProvider(BaseLLM):
    def __init__(self, api_key: str, model: str):
        self._client = Anthropic(api_key=api_key)
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
                history.append({"role": "assistant", "content": str(content)})
            else:
                history.append({"role": "user", "content": str(content)})

        system_text = "\n\n".join(system_parts) if system_parts else None
        return system_text, history

    def _build_params(self, config: GenerateConfig) -> dict:
        params: dict = {
            "temperature": config.temperature,
            "top_p": config.top_p,
            "max_tokens": config.max_tokens or 1024,
        }
        if config.stop is not None:
            params["stop_sequences"] = config.stop
        return params

    def generate(self, messages: list[dict], config: GenerateConfig | None = None) -> LLMResponse:
        config = config or GenerateConfig()
        system_text, history = self._split_messages(messages)

        response = self._client.messages.create(
            model=self._model,
            messages=history,
            system=system_text,
            **self._build_params(config),
        )

        text_parts = []
        for block in response.content:
            if getattr(block, "text", None):
                text_parts.append(block.text)

        usage = {}
        if getattr(response, "usage", None):
            usage = {
                "prompt_tokens": response.usage.input_tokens,
                "completion_tokens": response.usage.output_tokens,
                "total_tokens": response.usage.input_tokens + response.usage.output_tokens,
            }

        return LLMResponse(text="".join(text_parts), usage=usage)

    def generate_stream(
        self,
        messages: list[dict],
        config: GenerateConfig | None = None,
    ) -> Generator[str, None, None]:
        config = config or GenerateConfig()
        system_text, history = self._split_messages(messages)

        stream = self._client.messages.create(
            model=self._model,
            messages=history,
            system=system_text,
            stream=True,
            **self._build_params(config),
        )
        for event in stream:
            if event.type == "content_block_delta":
                text = getattr(event.delta, "text", "")
                if text:
                    yield text
