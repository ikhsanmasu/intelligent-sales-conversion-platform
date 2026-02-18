from openai import OpenAI

from app.core.llm.base import BaseLLM
from app.core.llm.schemas import GenerateConfig, LLMResponse


class XaiProvider(BaseLLM):
    def __init__(self, api_key: str, model: str):
        self._client = OpenAI(api_key=api_key, base_url="https://api.x.ai/v1")
        self._model = model

    def _build_params(self, messages: list[dict], config: GenerateConfig) -> dict:
        params = {
            "model": self._model,
            "messages": messages,
            "temperature": config.temperature,
            "top_p": config.top_p,
        }
        if config.max_tokens is not None:
            params["max_tokens"] = config.max_tokens
        if config.stop is not None:
            params["stop"] = config.stop
        return params

    def generate(self, messages: list[dict], config: GenerateConfig | None = None) -> LLMResponse:
        config = config or GenerateConfig()

        response = self._client.chat.completions.create(
            **self._build_params(messages, config),
        )
        return LLMResponse(
            text=response.choices[0].message.content,
            usage={
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            },
        )

    def generate_stream(self, messages: list[dict], config: GenerateConfig | None = None):
        config = config or GenerateConfig()

        stream = self._client.chat.completions.create(
            **self._build_params(messages, config),
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
